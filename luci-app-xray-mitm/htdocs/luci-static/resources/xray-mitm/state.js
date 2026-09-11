'use strict';
'require baseclass';

function arrayValue(value) {
	return Array.isArray(value) ? value : [];
}

function nodeId(item) {
	if (typeof item === 'string')
		return item;

	return item && (item.id || item.name || item.section);
}

function nodeItems(value) {
	return arrayValue(value).map(function(item) {
		var id = nodeId(item);

		return id ? { id: id, raw: item } : null;
	}).filter(function(item) { return !!item; });
}

function passwallSelection(passwall) {
	passwall = passwall || {};

	var shuntItems = passwall.shunt_nodes || passwall.shunts;
	var vpnItems = passwall.vpn_nodes || passwall.vpns;
	var shunts = nodeItems(shuntItems);
	var vpns = nodeItems(vpnItems);
	var selectedShunt = passwall.selected_shunt || passwall.current_shunt ||
		(shunts[0] && shunts[0].id);
	var selectedVpn = passwall.selected_vpn || (vpns[0] && vpns[0].id);

	return {
		shunts: shunts,
		vpns: vpns,
		selectedShunt: selectedShunt,
		selectedVpn: selectedVpn,
		compatible: passwall.available !== false && passwall.compatible === true &&
			shunts.length > 0 && vpns.length > 0
	};
}

function certificateSlot(certificates, name) {
	certificates = certificates || {};

	if (certificates.slots && certificates.slots[name])
		return certificates.slots[name];

	return certificates[name] || {};
}

function slotPresent(slot) {
	return !!(slot && (slot.present === true || slot.fingerprint));
}

function deriveSimpleState(setup, status, certificates, passwall) {
	setup = setup || {};
	status = status || {};
	certificates = certificates || {};
	passwall = passwall || {};

	var certificate = setup.certificate || {};
	var passwallState = setup.passwall2 || {};
	var routing = setup.routing || {};
	var selection = passwallSelection(passwall);
	var certificateReady = certificate.ready === true;
	var setupBlocked = certificate.candidate_requires_attention === true ||
		certificate.requires_attention === true;

	return {
		certificateReady: certificateReady,
		setupBlocked: setupBlocked,
		setupComplete: setup.ready === true && !!setup.service &&
			setup.service.boot_enabled === true,
		passwallInstalled: passwallState.installed === true,
		shuntAvailable: passwallState.shunt_available === true,
		vpnAvailable: passwallState.vpn_available === true,
		passwallCompatible: passwallState.compatible === true,
		mitmRunning: status.running === true,
		canReviewRouting: passwallState.compatible === true && passwall.writable === true &&
			routing.recovery_pending !== true && selection.shunts.length > 0 &&
			selection.vpns.length > 0,
		selectedVpn: selection.selectedVpn,
		selection: selection,
		routing: routing,
		passwallState: passwallState
	};
}

function routingChoices(routing) {
	routing = routing || {};

	return {
		gemini: routing.gemini === true,
		android_check: routing.android_check === true,
		youtube_control: routing.youtube_control === true,
		google_mitm: routing.google_mitm === true,
		meta_mitm: routing.meta_mitm === true,
		fastly_mitm: routing.fastly_mitm === true,
		iran_direct: routing.iran_direct === true,
		accounts_google: routing.accounts_google === true,
		set_default_vpn: routing.set_default_vpn === true,
		set_localhost_proxy_zero: routing.set_localhost_proxy_zero === true
	};
}

function recommendedChoices() {
	return {
		gemini: true,
		android_check: false,
		youtube_control: false,
		google_mitm: true,
		meta_mitm: false,
		fastly_mitm: false,
		iran_direct: true,
		accounts_google: false,
		set_default_vpn: false,
		set_localhost_proxy_zero: true
	};
}

function routingArguments(values) {
	values = values || {};

	return [
		values.shunt_node,
		values.vpn_node,
		values.gemini,
		values.android_check,
		values.youtube_control,
		values.google_mitm,
		values.meta_mitm,
		values.fastly_mitm,
		values.iran_direct,
		values.accounts_google,
		values.set_default_vpn,
		values.set_localhost_proxy_zero
	];
}

function routeStatus(source, active) {
	if (active)
		return { kind: 'active', tone: 'good' };
	if (source === 'existing')
		return { kind: 'existing', tone: 'info' };
	if (source === 'managed')
		return { kind: 'managed', tone: 'muted' };

	return { kind: 'new', tone: 'warn' };
}

function setupProgress(status, certificates, passwall) {
	status = status || {};
	var current = certificateSlot(certificates, 'current');
	var routing = (passwall && passwall.routing_state) || {};

	return {
		firstTime: status.configured !== true || !slotPresent(current),
		serviceReady: status.configured === true,
		certificateReady: slotPresent(current),
		mitmRunning: status.running === true,
		routingReady: routing.google_mitm === true || routing.gemini === true ||
			routing.iran_direct === true
	};
}

return baseclass.extend({
	certificateSlot: certificateSlot,
	deriveSimpleState: deriveSimpleState,
	nodeItems: nodeItems,
	passwallSelection: passwallSelection,
	recommendedChoices: recommendedChoices,
	routeStatus: routeStatus,
	routingArguments: routingArguments,
	routingChoices: routingChoices,
	setupProgress: setupProgress,
	slotPresent: slotPresent
});
