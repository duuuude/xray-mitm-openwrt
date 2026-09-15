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

var ROUTING_FIELDS = [
	'gemini', 'android_check', 'youtube_control', 'google_play',
	'google_mitm', 'google_meet', 'meta_mitm', 'fastly_mitm',
	'iran_direct', 'accounts_google', 'set_default_vpn',
	'set_localhost_proxy_zero'
];

var ROUTING_POLICY_FIELDS = {
	set_default_vpn: true,
	set_localhost_proxy_zero: true
};

function normalizeRoutingChoices(routing, fallback) {
	routing = routing || {};
	fallback = fallback || {};
	var choices = {};

	ROUTING_FIELDS.forEach(function(name) {
		var value = routing[name];

		if (value === undefined)
			value = fallback[name];

		choices[name] = value === true;
	});

	return choices;
}

function routingChoices(routing) {
	return normalizeRoutingChoices(routing);
}

function recommendedChoices() {
	return normalizeRoutingChoices({
		gemini: true,
		android_check: true,
		youtube_control: true,
		google_play: true,
		google_mitm: true,
		google_meet: true,
		meta_mitm: false,
		fastly_mitm: false,
		iran_direct: true,
		accounts_google: true,
		set_default_vpn: true,
		set_localhost_proxy_zero: true
	});
}

function routingArguments(values) {
	values = values || {};

	return [ values.shunt_node, values.vpn_node ].concat(ROUTING_FIELDS.map(function(name) {
		return values[name];
	}));
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

function routingFieldNames() {
	return ROUTING_FIELDS.slice();
}

function routingIsConfigured(routing) {
	routing = normalizeRoutingChoices(routing);

	for (var i = 0; i < ROUTING_FIELDS.length; i++)
		if (routing[ROUTING_FIELDS[i]] === true)
			return true;

	return false;
}

function routingHasServiceSelection(routing) {
	routing = normalizeRoutingChoices(routing);

	return ROUTING_FIELDS.some(function(name) {
		return !ROUTING_POLICY_FIELDS[name] && routing[name] === true;
	});
}

function routingMatchesRecommended(routing) {
	routing = normalizeRoutingChoices(routing);
	var recommended = recommendedChoices();

	for (var i = 0; i < ROUTING_FIELDS.length; i++) {
		var name = ROUTING_FIELDS[i];

		if ((routing[name] === true) !== (recommended[name] === true))
			return false;
	}

	return true;
}

function deriveBasicRoutingStatus(routing, fallback) {
	routing = routing || {};
	fallback = fallback || {};
	var configured = routing.configured;
	var recommended = routing.recommended_matches_current;

	if (configured === undefined)
		configured = routingIsConfigured(fallback);
	if (recommended === undefined && configured === true)
		recommended = routingMatchesRecommended(fallback);

	if (configured !== true)
		return { kind: 'not_configured', tone: 'warn' };
	if (recommended === true)
		return { kind: 'recommended', tone: 'good' };

	return { kind: 'custom', tone: 'good' };
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
		routingReady: routingHasServiceSelection(routing)
	};
}

return baseclass.extend({
	certificateSlot: certificateSlot,
	deriveSimpleState: deriveSimpleState,
	nodeItems: nodeItems,
	passwallSelection: passwallSelection,
	normalizeRoutingChoices: normalizeRoutingChoices,
	routingHasServiceSelection: routingHasServiceSelection,
	recommendedChoices: recommendedChoices,
	deriveBasicRoutingStatus: deriveBasicRoutingStatus,
	routeStatus: routeStatus,
	routingFieldNames: routingFieldNames,
	routingArguments: routingArguments,
	routingChoices: routingChoices,
	setupProgress: setupProgress,
	slotPresent: slotPresent
});
