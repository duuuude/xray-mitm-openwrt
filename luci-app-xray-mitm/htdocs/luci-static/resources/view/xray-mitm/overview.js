'use strict';
'require view';
'require rpc';
'require ui';
'require dom';
'require xray-mitm.state as state';
'require xray-mitm.ui as uiHelpers';

/* Keep this fallback synchronized with xray-mitm/Makefile PKG_VERSION. */
var PROJECT_VERSION = '0.4.3';

var callGetStatus = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'getStatus',
	expect: { '': {} }
});

var callGetSetupStatus = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'getSetupStatus',
	expect: { '': {} }
});

var callSetupRecommended = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'setupRecommended',
	expect: { '': {} }
});

var callHealth = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'runHealthCheck',
	expect: { '': {} }
});

var callServiceAction = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'serviceAction',
	params: [ 'action' ],
	expect: { '': {} }
});

var callInstallConfig = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'installDefaultConfig',
	expect: { '': {} }
});

var callGetCertificates = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'getCertificateStatus',
	expect: { '': {} }
});

var callExportCertificate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'exportCertificate',
	params: [ 'slot' ],
	expect: { '': {} }
});

var callGenerateCandidate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'generateCandidate',
	params: [ 'common_name', 'days' ],
	expect: { '': {} }
});

var callImportCandidate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'importCandidate',
	params: [ 'certificate_pem', 'private_key_pem' ],
	expect: { '': {} }
});

var callActivateCandidate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'activateCandidate',
	params: [ 'expected_fingerprint' ],
	expect: { '': {} }
});

var callDiscardCandidate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'discardCandidate',
	params: [ 'expected_fingerprint' ],
	expect: { '': {} }
});

var callRollbackCertificate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'rollbackCertificate',
	params: [ 'expected_current_fingerprint' ],
	expect: { '': {} }
});

var callAdoptLegacyCertificate = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'adoptLegacyCertificate',
	expect: { '': {} }
});

var callInspectPassWall2 = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'inspectPassWall2',
	expect: { '': {} }
});

var callRecoverPassWall2 = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'recoverPassWall2',
	expect: { '': {} }
});

var routingParams = [ 'shunt_node', 'vpn_node' ].concat(state.routingFieldNames());

var ROUTING_POLL_INTERVAL = 2000;
var ROUTING_POLL_ATTEMPTS = 75;

var text = uiHelpers.text;
var textNode = uiHelpers.textNode;
var assertOk = uiHelpers.assertOk;
var notification = uiHelpers.notification;
var setBusy = uiHelpers.setBusy;
var readSelectedFile = uiHelpers.readSelectedFile;
var slotData = uiHelpers.slotData;
var slotPresent = uiHelpers.slotPresent;
var optionList = uiHelpers.optionList;
var selectControl = uiHelpers.selectControl;
var statusPill = uiHelpers.statusPill;
var routeStatus = uiHelpers.routeStatus;
var simpleCheck = uiHelpers.simpleCheck;
var routingRuleCard = uiHelpers.routingRuleCard;
var operationList = uiHelpers.operationList;

var callPlanPassWall2 = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'planPassWall2',
	params: routingParams,
	expect: { '': {} }
});

var callApplyPassWall2 = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'applyPassWall2',
	params: [ 'token' ],
	expect: { '': {} }
});

var callPassWall2Activation = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'passWall2Activation',
	params: [ 'transaction' ],
	expect: { '': {} }
});

var callRollbackPassWall2 = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'rollbackPassWall2',
	params: [ 'transaction' ],
	expect: { '': {} }
});

function certificateRows(data) {
	var canExport = data && data.ok === true && data.recovery_pending !== true &&
		data.invalid_pair !== true;

	return [ 'current', 'candidate', 'previous' ].map(function(name) {
		var slot = slotData(data, name);
		var label = {
			current: _('Current'),
			candidate: _('Candidate'),
			previous: _('Previous')
		}[name];

			return E('tr', { class: 'tr' }, [
				E('td', { class: 'td left' }, label),
				E('td', { class: 'td left' }, slotPresent(slot) ?
					textNode(slot.common_name || slot.subject, _('Available')) : _('Not present')),
				E('td', { class: 'td left', style: 'font-family:monospace; word-break:break-all' },
					slotPresent(slot) ? textNode(slot.fingerprint) : '—'),
				E('td', { class: 'td left' }, slotPresent(slot) ?
					textNode(slot.not_after || slot.notAfter || slot.expires) : '—'),
			E('td', { class: 'td left' }, slotPresent(slot) && canExport ? E('button', {
				class: 'btn cbi-button-neutral',
				click: function(ev) {
					var button = ev.currentTarget;
					setBusy(button, true);
					callExportCertificate(name).then(assertOk).then(function(result) {
						var blob = new Blob([ result.certificate_pem ], { type: 'application/x-pem-file' });
						var url = URL.createObjectURL(blob);
						var link = document.createElement('a');
						link.href = url;
						link.download = 'xray-mitm-' + name + '-ca.crt';
						document.body.appendChild(link);
						link.click();
						link.remove();
						window.setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
					}).catch(function(error) {
						notification(error.message, 'error');
					}).then(function() { setBusy(button, false); });
				}
			}, _('Download public CA')) : '—')
		]);
	});
}

return view.extend({
	load: function() {
		return Promise.all([
			callGetSetupStatus(),
			callGetStatus(),
			callGetCertificates(),
			callInspectPassWall2()
		]);
	},

	reloadPage: function() {
		window.setTimeout(function() { window.location.reload(); }, 500);
	},

	setRoutingBusyMessage: function(title, detail) {
		var titleNode = document.getElementById('xray-mitm-routing-busy-title');
		var detailNode = document.getElementById('xray-mitm-routing-busy-detail');

		if (titleNode)
			titleNode.textContent = text(title);
		if (detailNode)
			detailNode.textContent = text(detail);
	},

	setRoutingBusy: function(busy) {
		var overlay = document.getElementById('xray-mitm-routing-busy');

		if (!busy) {
			if (this.routingBusyTimer !== null && this.routingBusyTimer !== undefined)
				window.clearInterval(this.routingBusyTimer);

			this.routingBusyTimer = null;
			this.routingBusy = false;
			if (overlay && overlay.parentNode)
				overlay.parentNode.removeChild(overlay);
			if (document.documentElement)
				document.documentElement.removeAttribute('aria-busy');
			return;
		}

		if (this.routingBusy || !document.body)
			return;

		this.routingBusy = true;
		this.routingBusyStartedAt = Date.now();
		overlay = E('div', {
			id: 'xray-mitm-routing-busy',
			role: 'dialog',
			'aria-modal': 'true',
			'aria-live': 'polite',
			'aria-labelledby': 'xray-mitm-routing-busy-title',
			'tabindex': '-1',
			keydown: function(ev) {
				if (ev.key === 'Escape' || ev.key === 'Tab')
					ev.preventDefault();
			},
			style: 'position:fixed;inset:0;z-index:10000;display:flex;align-items:center;' +
				'justify-content:center;padding:1.5rem;background:rgba(0,0,0,.64);cursor:wait'
		}, [
			E('div', {
				style: 'width:100%;max-width:34rem;padding:1.5rem;border:1px solid var(--border-color-medium,#ccc);' +
					'border-radius:.55rem;background:var(--background-color-high,#222);' +
					'box-shadow:0 1rem 3rem rgba(0,0,0,.4);text-align:center'
			}, [
				E('div', { style: 'font-size:2rem;line-height:1;margin-bottom:.8rem' }, '⏳'),
				E('h3', { id: 'xray-mitm-routing-busy-title', style: 'margin:.2rem 0 .65rem' },
					_('Applying routing changes…')),
				E('p', { id: 'xray-mitm-routing-busy-detail', style: 'margin:.4rem 0' },
					_('PassWall2 is restarting and checking the new rules. Please keep this page open.')),
				E('p', { id: 'xray-mitm-routing-busy-elapsed', style: 'margin:.8rem 0;font-weight:600' },
					_('Elapsed time: 0 seconds')),
				E('small', { style: 'display:block;opacity:.78' },
					_('All routing controls are locked until the router confirms completion.'))
			])
		]);
		document.body.appendChild(overlay);
		if (document.documentElement)
			document.documentElement.setAttribute('aria-busy', 'true');

		var startedAt = this.routingBusyStartedAt;
		var updateElapsed = function() {
			var elapsed = document.getElementById('xray-mitm-routing-busy-elapsed');
			var seconds = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));

			if (elapsed)
				elapsed.textContent = _('Elapsed time: ') + seconds + _(' seconds');
		};

		updateElapsed();
		this.routingBusyTimer = window.setInterval(updateElapsed, 1000);
		overlay.focus();
	},

	runMutation: function(button, promise, successMessage, reload) {
		setBusy(button, true);

		return promise.then(assertOk).then(L.bind(function(result) {
			notification(result.message || successMessage, 'info');
			if (reload)
				this.reloadPage();
			return result;
		}, this)).catch(function(error) {
			notification(error.message, 'error');
		}).then(function(result) {
			setBusy(button, false);
			return result;
		});
	},

	serviceAction: function(action, ev) {
		if ((action === 'stop' || action === 'disable') &&
			!window.confirm(_('This can interrupt traffic currently using the MITM route. Continue?')))
			return;

		this.runMutation(ev.currentTarget, callServiceAction(action),
			_('Service action completed.'), true);
	},

	setupRecommended: function(ev) {
		this.runMutation(ev.currentTarget, callSetupRecommended(),
			_('Automatic setup completed.'), true);
	},

	downloadCurrentCertificate: function(ev) {
		var button = ev.currentTarget;
		setBusy(button, true);
		callExportCertificate('current').then(assertOk).then(function(result) {
			var blob = new Blob([ result.certificate_pem ], { type: 'application/x-pem-file' });
			var url = URL.createObjectURL(blob);
			var link = document.createElement('a');
			link.href = url;
			link.download = 'xray-mitm-ca.crt';
			document.body.appendChild(link);
			link.click();
			link.remove();
			window.setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
		}).catch(function(error) {
			notification(error.message, 'error');
		}).then(function() { setBusy(button, false); });
	},

	installConfig: function(ev) {
		if (!window.confirm(_(
			'Install the packaged default configuration? This only works when config.json does not already exist.'
		)))
			return;

		this.runMutation(ev.currentTarget, callInstallConfig(),
			_('Default configuration installed.'), true);
	},

	runHealth: function(ev) {
		var button = ev.currentTarget;
		var output = document.getElementById('xray-mitm-health-output');
		setBusy(button, true);
		if (output)
			output.textContent = _('Running health check…');
		this.setSimpleHealthStatus(_('Checking…'), 'info');

		callHealth().then(function(result) {
			if (!result || result.ok === false) {
				var error = new Error(result && result.error ? result.error : _('Health check failed.'));
				error.details = result && (result.output || result.details || result.message);
				throw error;
			}

			var lines = result.lines || result.details || result.output || result.message;
			if (output)
				output.textContent = Array.isArray(lines) ? lines.join('\n') : text(lines, _('Health check passed.'));
			this.setSimpleHealthStatus(_('Working'), 'good');
			notification(_('MITM health check passed.'), 'info');
		}.bind(this)).catch(function(error) {
			if (output)
				output.textContent = text(error.details || error.message, _('Health check failed.'));
			this.setSimpleHealthStatus(_('Needs attention'), 'warn');
			notification(_('MITM health check failed.'), 'error');
		}.bind(this)).then(function() { setBusy(button, false); });
	},

	setSimpleHealthStatus: function(label, tone) {
		var target = document.getElementById('xray-mitm-simple-health');
		if (target)
			dom.content(target, statusPill(label, tone));
	},

	pageNavigation: function() {
		var groups = [
			{ name: 'basic', label: _('Basic') },
			{ name: 'advanced', label: _('Advanced') }
		];
		var advancedPages = [
			{ name: 'overview', label: _('Overview') },
			{ name: 'service', label: _('Service') },
			{ name: 'routing', label: _('Routing') },
			{ name: 'certificates', label: _('Certificates') }
		];
		var basicPages = [
			{ name: 'overview', label: _('Overview') },
			{ name: 'setup', label: _('Setup') },
			{ name: 'routing', label: _('Routing') },
			{ name: 'status', label: _('Status') }
		];
		var tabRow = function(items, mode, active, style) {
			return E('ul', {
				class: 'cbi-tabmenu',
				'data-dashboard-tabs': mode,
				style: style || ''
			}, items.map(function(item) {
				return E('li', {
					class: item.name === active ? 'cbi-tab' : 'cbi-tab-disabled',
					'data-dashboard-tab-mode': mode,
					'data-dashboard-tab-page': item.name
				}, E('a', {
					href: '#',
					click: ui.createHandlerFn(this, 'switchDashboardPage', mode, item.name)
				}, item.label));
			}, this));
		}.bind(this);

		return E('nav', { 'aria-label': _('MITM Domain Fronting pages') }, [
			tabRow(groups, 'mode', 'basic'),
			tabRow(basicPages, 'basic', 'overview'),
			tabRow(advancedPages, 'advanced', '', 'display:none')
		]);
	},

	switchDashboardPage: function(mode, page) {
		var targetPage = mode === 'mode' ? 'overview' : page;
		var targetMode = mode === 'mode' ? page : mode;
		var simple = document.getElementById('xray-mitm-simple');
		var advanced = document.getElementById('xray-mitm-advanced');

		if (simple)
			simple.style.display = targetMode === 'basic' ? '' : 'none';
		if (advanced)
			advanced.style.display = targetMode === 'advanced' ? '' : 'none';

		document.querySelectorAll('[data-dashboard-panel-mode]').forEach(function(panel) {
			panel.style.display = panel.getAttribute('data-dashboard-panel-mode') === targetMode &&
				panel.getAttribute('data-dashboard-panel-page') === targetPage ? '' : 'none';
		});
		document.querySelectorAll('[data-dashboard-tabs]').forEach(function(row) {
			var name = row.getAttribute('data-dashboard-tabs');
			row.style.display = name === 'mode' || name === targetMode ? '' : 'none';
		});
		document.querySelectorAll('[data-dashboard-tab-mode]').forEach(function(tab) {
			var tabMode = tab.getAttribute('data-dashboard-tab-mode');
			var tabPage = tab.getAttribute('data-dashboard-tab-page');
			var active = tabMode === 'mode' ? tabPage === targetMode :
				tabMode === targetMode && tabPage === targetPage;
			tab.className = active ? 'cbi-tab' : 'cbi-tab-disabled';
		});
	},

		reviewRecommendedRouting: function(ev) {
		var shunts = optionList(this.passwall.shunt_nodes || this.passwall.shunts);
		var vpns = optionList(this.passwall.vpn_nodes || this.passwall.vpns);
		var shunt = this.passwall.selected_shunt || (shunts[0] && shunts[0].id);
		var vpnControl = document.getElementById('xray-mitm-simple-vpn');
		var vpn = vpnControl ? vpnControl.value : (this.passwall.selected_vpn || (vpns[0] && vpns[0].id));
		var output = document.getElementById('xray-mitm-simple-routing-preview');
		var button = ev.currentTarget;
		var currentRouting = this.passwall.routing_state || {};
		var values = state.routingChoices(this.simpleHiddenRouting || currentRouting);
		[ 'gemini', 'android_check', 'youtube_control', 'google_play', 'google_mitm', 'google_meet', 'meta_mitm',
			'fastly_mitm', 'iran_direct', 'accounts_google' ].forEach(function(name) {
			var choice = document.getElementById('xray-mitm-simple-route-' + name.replace(/_/g, '-'));
			if (choice)
				values[name] = choice.checked;
		});
		values.shunt_node = shunt;
		values.vpn_node = vpn;
		setBusy(button, true);
		callPlanPassWall2.apply(null, routingParams.map(function(name) { return values[name]; })).then(assertOk).then(L.bind(function(plan) {
			this.planToken = plan.no_change === true ? null : (plan.token || null);
			var blocked = plan.requires_mitm_running === true && this.status.running !== true;
			var vpnSelected = values.gemini || values.android_check || values.youtube_control || values.google_play || values.accounts_google;
			var mitmSelected = values.google_mitm || values.google_meet || values.meta_mitm || values.fastly_mitm;
			var children = [
				E('h4', {}, plan.no_change === true ? _('Selected routing is already active') : _('Ready to configure selected routing')),
				E('div', { style: 'display:grid;gap:.45rem;margin:.75rem 0' }, [
					this.simpleRouteRow(_('VPN Overrides'), vpnSelected ? _('Selected VPN') : _('Not selected')),
					this.simpleRouteRow(_('MITM-Compatible Services'), mitmSelected ? _('Local SOCKS') : _('Not selected')),
					this.simpleRouteRow(_('Regional Direct Access'), values.iran_direct ? _('Direct connection') : _('Not selected'))
				]),
				E('p', { style: 'opacity:.82' }, _('This reflects the checkboxes above. Existing custom rules are preserved, and nothing changes until you apply this preview.')),
				E('p', { style: 'opacity:.82' }, _('Applying this routing may briefly interrupt traffic. Keep this page open while PassWall2 restarts and confirms the changes.'))
			];
			if (blocked)
				children.push(E('div', { class: 'alert-message warning' }, _('Start MITM before applying this routing setup.')));
			if (this.planToken && !blocked)
				children.push(E('button', {
					class: 'btn cbi-button-positive',
					click: ui.createHandlerFn(this, 'applyRouting')
				}, _('Apply selected routing')));
			dom.content(output, children);
		}, this)).catch(function(error) {
			dom.content(output, E('div', { class: 'alert-message danger' }, textNode(error.message)));
		}).then(function() { setBusy(button, false); });
	},

	setSimpleRoutingChoices: function(values) {
		Object.keys(values).forEach(function(name) {
			var element = document.getElementById('xray-mitm-simple-route-' + name.replace(/_/g, '-'));
			if (element && element.type === 'checkbox')
				element.checked = values[name] === true;
		});

		this.routingSelectionChanged();
	},

	useSimpleRecommendedRouting: function() {
		this.simpleHiddenRouting = state.recommendedChoices();
		this.setSimpleRoutingChoices(this.simpleHiddenRouting);
	},

	generateCandidate: function(ev) {
		var name = document.getElementById('xray-mitm-ca-cn').value;
		var days = Number(document.getElementById('xray-mitm-ca-days').value);

		this.runMutation(ev.currentTarget, callGenerateCandidate(name, days),
			_('Candidate CA generated. Download and trust its public certificate before activation.'), true);
	},

	importCandidate: function(ev) {
		if (window.location.protocol !== 'https:' || window.isSecureContext === false) {
			notification(_('Private-key import is available only when LuCI is opened through HTTPS.'), 'error');
			return;
		}

		var button = ev.currentTarget;
		var certInput = document.getElementById('xray-mitm-import-cert');
		var keyInput = document.getElementById('xray-mitm-import-key');
		setBusy(button, true);

		Promise.all([
			readSelectedFile(certInput, 32 * 1024),
			readSelectedFile(keyInput, 64 * 1024)
		]).then(function(files) {
			return callImportCandidate(files[0], files[1]);
		}).then(assertOk).then(L.bind(function(result) {
			certInput.value = '';
			keyInput.value = '';
			notification(result.message || _('Certificate pair imported as a candidate.'), 'info');
			this.reloadPage();
		}, this)).catch(function(error) {
			certInput.value = '';
			keyInput.value = '';
			notification(error.message, 'error');
		}).then(function() { setBusy(button, false); });
	},

	activateCandidate: function(ev) {
		var candidate = slotData(this.certificates, 'candidate');

		if (!candidate.fingerprint)
			return;

		if (!window.confirm(_(
			'Activate this candidate CA and restart only xray-mitm? Clients that do not trust it will fail certificate validation.'
		)))
			return;

		this.runMutation(ev.currentTarget, callActivateCandidate(candidate.fingerprint),
			_('Candidate CA activated.'), true);
	},

	discardCandidate: function(ev) {
		var candidate = slotData(this.certificates, 'candidate');

		if (!candidate.fingerprint || !window.confirm(_('Discard the candidate certificate pair?')))
			return;

		this.runMutation(ev.currentTarget, callDiscardCandidate(candidate.fingerprint),
			_('Candidate CA discarded.'), true);
	},

	rollbackCertificate: function(ev) {
		var current = slotData(this.certificates, 'current');

		if (!current.fingerprint || !window.confirm(_(
			'Restore the previous CA and restart only xray-mitm?'
		)))
			return;

		this.runMutation(ev.currentTarget, callRollbackCertificate(current.fingerprint),
			_('Previous CA restored.'), true);
	},

	adoptLegacyCertificate: function(ev) {
		if (!window.confirm(_(
			'Validate and adopt the existing /etc/xray-mitm certificate pair? Originals are restored if validation or restart fails.'
		)))
			return;

		this.runMutation(ev.currentTarget, callAdoptLegacyCertificate(),
			_('Existing certificate pair adopted.'), true);
	},

	planRouting: function(ev) {
		var values = {};
		routingParams.forEach(function(name) {
			var element = document.getElementById('xray-mitm-route-' + name.replace(/_/g, '-'));
			values[name] = element && element.type === 'checkbox' ? element.checked :
				(element ? element.value : false);
		});
		var button = ev.currentTarget;
		var output = document.getElementById('xray-mitm-routing-preview');
		setBusy(button, true);

		callPlanPassWall2.apply(null, routingParams.map(function(name) { return values[name]; })).then(assertOk).then(L.bind(function(plan) {
			this.planToken = plan.no_change === true ? null : (plan.token || null);
			this.lastPlan = plan;
			var mitmRequiredButStopped = plan.requires_mitm_running === true &&
				(!this.status || this.status.running !== true);
			dom.content(output, [
				E('h4', {}, _('Preview')),
				operationList(plan),
				mitmRequiredButStopped ? E('div', { class: 'alert-message danger' }, _(
					'Start MITM Domain Fronting before applying this preview. MITM-Compatible Services would otherwise point to an unavailable local SOCKS listener.'
				)) : '',
					plan.warning ? E('div', { class: 'alert-message warning' }, textNode(plan.warning)) : ''
				]);

			var apply = document.getElementById('xray-mitm-routing-apply');
			apply.disabled = !this.planToken || mitmRequiredButStopped || plan.writable === false ||
				(this.passwall.capabilities && this.passwall.capabilities.apply === false);
		}, this)).catch(function(error) {
				dom.content(output, E('div', { class: 'alert-message danger' }, textNode(error.message)));
		}).then(function() { setBusy(button, false); });
	},

	applyRouting: function(ev) {
		if (this.routingBusy || !this.planToken || !window.confirm(_(
			'Apply exactly the previewed PassWall2 changes and restart PassWall2? A rollback snapshot will be kept.'
		)))
			return;

		var button = ev.currentTarget;
		var output = document.getElementById('xray-mitm-routing-preview');
		this.setRoutingBusy(true);
		setBusy(button, true);
		notification(_('Applying PassWall2 routing changes. Keep this page open until it finishes.'), 'info');

		callApplyPassWall2(this.planToken).then(assertOk).then(L.bind(function(result) {
			if (!result.pending || !result.transaction)
				throw new Error(_('The routing activation was not accepted.'));

			this.planToken = null;
			this.routingActivation = result.transaction;
			this.setRoutingBusyMessage(_('PassWall2 is restarting…'), _(
				'The router is applying the reviewed rules. The controls are locked until activation is confirmed.'
			));
			dom.content(output, E('div', { class: 'alert-message warning' }, _(
				'PassWall2 is restarting. Keep this page open while the router confirms the activation or exact rollback.'
			)));
			this.pollRoutingActivation(result.transaction, button, output, 0);
		}, this)).catch(function(error) {
			this.setRoutingBusy(false);
			setBusy(button, false);
			notification(error.message, 'error');
		}.bind(this));
	},

	pollRoutingActivation: function(transaction, button, output, attempts) {
		callPassWall2Activation(transaction).then(assertOk).then(L.bind(function(status) {
			if (status.pending === true) {
				this.setRoutingBusyMessage(_('Waiting for PassWall2…'), _(
					'The router is still applying the change. It will unlock this page after verification.'
				));
				window.setTimeout(L.bind(this.pollRoutingActivation, this, transaction, button, output, attempts + 1), ROUTING_POLL_INTERVAL);
				return;
			}

			var result = status.result || {};
			if (result.ok !== true) {
				this.setRoutingBusy(false);
				setBusy(button, false);
				dom.content(output, E('div', { class: 'alert-message danger' }, textNode(
					result.message || _('Routing activation failed. The recorded recovery state must be reviewed before another change.')
				)));
				notification(result.message || _('PassWall2 routing activation failed.'), 'error');
				return;
			}

			this.rollbackTransaction = result.transaction || null;
			this.routingActivation = null;
			this.setRoutingBusyMessage(_('Routing changes applied'), _('The router confirmed the new PassWall2 rules. Reloading this page…'));
			setBusy(button, false);
			notification(_('PassWall2 routing changes applied.'), 'info');
			this.reloadPage();
		}, this)).catch(L.bind(function(error) {
			if (attempts < ROUTING_POLL_ATTEMPTS) {
				this.setRoutingBusyMessage(_('Waiting for PassWall2…'), _(
					'The router did not answer this check yet. Retrying automatically; keep this page open.'
				));
				window.setTimeout(L.bind(this.pollRoutingActivation, this, transaction, button, output, attempts + 1), ROUTING_POLL_INTERVAL);
				return;
			}
			setBusy(button, false);
			this.setRoutingBusy(false);
			dom.content(output, E('div', { class: 'alert-message danger' }, textNode(
				_('Could not read the routing activation result. Reopen this page to check its recorded status.')
			)));
			notification(error.message, 'error');
		}, this));
	},

	rollbackRouting: function(ev) {
		if (!this.rollbackTransaction || !window.confirm(_(
			'Restore the exact PassWall2 file from the last transaction?'
		)))
			return;

		this.runMutation(ev.currentTarget, callRollbackPassWall2(this.rollbackTransaction),
			_('Routing transaction rolled back.'), true);
	},

	recoverRouting: function(ev) {
		if (!window.confirm(_(
			'Restore the exact PassWall2 file recorded before the interrupted transaction and restart PassWall2 if it is enabled?'
		)))
			return;

		this.runMutation(ev.currentTarget, callRecoverPassWall2(),
			_('Interrupted PassWall2 transaction recovered.'), true);
	},

	routingSelectionChanged: function() {
		if (this.routingBusy)
			return;

		this.planToken = null;
		this.lastPlan = null;
		var apply = document.getElementById('xray-mitm-routing-apply');
		if (apply)
			apply.disabled = true;

		var output = document.getElementById('xray-mitm-routing-preview');
		if (output)
			dom.content(output, E('p', { style: 'opacity:.8' }, _(
				'Selections changed. Review the setup again before applying.'
			)));

		var simpleOutput = document.getElementById('xray-mitm-simple-routing-preview');
		if (simpleOutput)
			dom.content(simpleOutput, E('p', { style: 'opacity:.8' }, _(
				'Selections changed. Review the routing rules again before applying.'
			)));
	},

	setRoutingChoices: function(values) {
		Object.keys(values).forEach(function(name) {
			var element = document.getElementById('xray-mitm-route-' + name.replace(/_/g, '-'));
			if (element && element.type === 'checkbox')
				element.checked = values[name] === true;
		});

		this.routingSelectionChanged();
	},

	useRecommendedRouting: function() {
		this.setRoutingChoices(state.recommendedChoices());
	},

	restoreCurrentRouting: function() {
		var routingState = (this.passwall && this.passwall.routing_state) || {};
		this.setRoutingChoices(state.routingChoices(routingState));
	},

	simpleStateRow: function(label, value, tone, detail) {
		return E('div', {
			style: 'display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;' +
				'padding:.7rem 0;border-bottom:1px solid var(--border-color-low,#ddd)'
		}, [
			E('div', {}, [
				E('strong', {}, label),
				detail ? E('small', { style: 'display:block;margin-top:.15rem;opacity:.78' }, detail) : ''
			]),
			statusPill(value, tone)
		]);
	},

	simpleRouteRow: function(label, destination) {
		return E('div', {
			style: 'display:grid;grid-template-columns:minmax(10rem,1fr) auto;gap:1rem;' +
				'align-items:center;padding:.45rem 0'
		}, [ E('strong', {}, label), E('span', {}, '→ ' + destination) ]);
	},

	simpleRoutingSummary: function() {
		return E('div', {
			class: 'xray-mitm-routing-summary',
			style: 'padding:.85rem 1rem;margin:1rem 0;border:1px solid var(--border-color-medium,#ccc);' +
				'border-radius:.45rem;background:rgba(128,128,128,.06)'
		}, [
			E('h4', { style: 'margin-top:0' }, _('Recommended routing')),
			E('p', {}, _('The recommended preset sends only these tested service groups to each destination. Expand Customize routing to change individual groups.')),
			E('div', { style: 'display:grid;gap:.1rem;margin:.7rem 0' }, [
				this.simpleRouteRow(_('Gemini and Google app/control traffic'), _('Selected VPN')),
				this.simpleRouteRow(_('Google Drive and YouTube video'), _('Local SOCKS (MITM)')),
				this.simpleRouteRow(_('Google Meet web and signaling'), _('Local SOCKS (MITM)')),
				this.simpleRouteRow(_('Iranian sites and IP addresses'), _('Direct connection'))
			]),
			E('p', { style: 'margin-bottom:0;opacity:.82' }, _('Meet audio and video media may use UDP or separate media IPs, so test a real call before relying on MITM for every part of a meeting.'))
		]);
	},

	simpleStatusCard: function(label, value, tone, detail) {
		return E('div', {
			style: 'padding:.85rem 1rem;border:1px solid var(--border-color-medium,#ccc);' +
				'border-radius:.45rem;background:rgba(128,128,128,.06)'
		}, [
			E('small', { style: 'display:block;opacity:.75;margin-bottom:.35rem' }, label),
			statusPill(value, tone),
			detail ? E('small', { style: 'display:block;margin-top:.4rem;opacity:.75' }, detail) : ''
		]);
	},

	overviewStatusStrip: function(status, certificates, passwall) {
		var passwallState = (this.setup && this.setup.passwall2) || {};
		var routingState = (passwall && passwall.routing_state) || {};
		var current = slotData(certificates, 'current');
		var cards = [
			{
				icon: '◆', label: _('MITM service'),
				value: status.running === true ? _('Running') : _('Stopped'),
				tone: status.running === true ? 'good' : 'warn', detail: '127.0.0.1:10808'
			},
			{
				icon: '◉', label: _('PassWall2'),
				value: passwallState.installed === true ? _('Ready') : _('Not detected'),
				tone: passwallState.installed === true ? 'good' : 'warn', detail: _('Routing integration')
			},
			{
				icon: '↔', label: _('PassWall2 routing'),
				value: passwallState.shunt_available === true && passwallState.vpn_available === true ?
					_('Ready') : _('Needs attention'),
				tone: passwallState.shunt_available === true && passwallState.vpn_available === true ? 'good' : 'warn',
				detail: routingState.configured === true ? _('Rules configured') : _('Choose your rules')
			},
			{
				icon: '✓', label: _('Public certificate'),
				value: slotPresent(current) ? _('Ready') : _('Needed'),
				tone: slotPresent(current) ? 'good' : 'warn', detail: _('Private key stays on router')
			}
		];
		var toneColors = { good: '#2f7d32', warn: '#a15c00' };

		return E('div', {}, [
			E('style', {}, '@media(max-width:900px){.xray-mitm-status-strip,.xray-mitm-step-strip{grid-template-columns:repeat(2,minmax(0,1fr))!important}}' +
				'@media(max-width:520px){.xray-mitm-status-strip,.xray-mitm-step-strip{grid-template-columns:1fr!important}}'),
			E('div', {
				class: 'xray-mitm-status-strip',
				style: 'display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;' +
					'align-items:stretch;gap:.7rem;width:100%;box-sizing:border-box;' +
					'padding:.75rem;margin:1rem 0;border:1px solid var(--border-color-medium,#ccc);' +
					'border-radius:.35rem;background:rgba(128,128,128,.12)'
			}, cards.map(function(card) {
			return E('div', {
				class: 'xray-mitm-status-card',
				style: 'display:flex;align-items:center;gap:.8rem;width:100%;min-height:5.25rem;' +
					'padding:.75rem .9rem;border:1px solid var(--border-color-medium,#ccc);' +
					'border-radius:.35rem;background:rgba(0,0,0,.12);box-sizing:border-box'
			}, [
				E('span', {
					'aria-hidden': 'true',
					style: 'display:inline-flex;align-items:center;justify-content:center;width:2.35rem;height:2.35rem;' +
						'flex:0 0 2.35rem;border-radius:50%;background:rgba(94,114,228,.16);' +
						'color:#5e72e4;font-size:1.35rem;font-weight:700'
				}, card.icon),
				E('div', { style: 'min-width:0' }, [
					E('strong', { style: 'display:block;line-height:1.2' }, card.label),
					E('span', { style: 'display:block;margin-top:.2rem;font-weight:700;color:' + toneColors[card.tone] }, card.value),
					E('small', { style: 'display:block;margin-top:.15rem;opacity:.72;white-space:nowrap;overflow:hidden;text-overflow:ellipsis' }, card.detail)
				])
			]);
			}))
		]);
	},

	simpleRoutingTable: function(routing, passwall) {
		routing = routing || {};
		passwall = passwall || {};
		var ruleSources = passwall.rule_sources || {};
		var onChange = L.bind(this.routingSelectionChanged, this);
		var rows = [
			{ group: _('VPN Overrides'), source: 'vpn_overrides', name: 'gemini', label: _('Gemini app and API'), domains: 'gemini.google.com, generativelanguage.googleapis.com', destination: _('Selected VPN') },
			{ group: _('VPN Overrides'), source: 'vpn_overrides', name: 'android_check', label: _('Android internet checks'), domains: 'connectivitycheck.gstatic.com, connectivitycheck.android.com, clients3.google.com', destination: _('Selected VPN') },
			{ group: _('VPN Overrides'), source: 'vpn_overrides', name: 'youtube_control', label: _('YouTube sign-in and controls'), domains: _('YouTube UI/API domains; googlevideo.com uses Google MITM only when that optional route is enabled'), destination: _('Selected VPN') },
			{ group: _('VPN Overrides'), source: 'vpn_overrides', name: 'google_play', label: _('Google Play and Android services'), domains: _('Google Play, Android authentication, check-in, and download endpoints; bypasses MITM for native-app compatibility'), destination: _('Selected VPN') },
			{ group: _('VPN Overrides'), source: 'vpn_overrides', name: 'accounts_google', label: _('Google Account sign-in'), domains: 'accounts.google.com', destination: _('Selected VPN') },
			{ group: _('MITM-Compatible Services'), source: 'mitm_services', name: 'google_mitm', label: _('Google Drive and YouTube video'), domains: _('Selected Drive API/upload and googlevideo.com domains only; this is not all Google services. Google Play remains on the VPN override.'), destination: _('Local SOCKS') },
			{ group: _('MITM-Compatible Services'), source: 'mitm_services', name: 'google_meet', label: _('Google Meet web and signaling'), domains: _('Meet web and signaling hostnames; audio/video media may use UDP or separate media IPs, so test a real call before relying on MITM.'), destination: _('Local SOCKS') },
			{ group: _('MITM-Compatible Services'), source: 'mitm_services', name: 'meta_mitm', label: _('Meta websites'), domains: 'geosite:meta', destination: _('Local SOCKS') },
			{ group: _('MITM-Compatible Services'), source: 'mitm_services', name: 'fastly_mitm', label: _('Fastly-backed websites'), domains: _('Fastly, Reddit, CNN, and BuzzFeed groups'), destination: _('Local SOCKS') },
			{ group: _('Regional Direct Access'), source: 'regional_direct', name: 'iran_direct', label: _('Iranian websites and IP addresses'), domains: 'geosite:ir, geoip:ir', destination: _('Direct connection') }
		];
		var lastGroup = null;
		var body = [];

		rows.forEach(function(row) {
			if (row.group !== lastGroup) {
				body.push(E('tr', { class: 'tr table-titles' }, [
					E('th', { class: 'th left', colspan: '5' }, row.group)
				]));
				lastGroup = row.group;
			}

			var checked = routing[row.name] === true;
			var status = routeStatus(ruleSources[row.source], checked);
			body.push(E('tr', { class: 'tr' }, [
				E('td', { class: 'td', style: 'width:3rem;text-align:center' }, E('input', {
					id: 'xray-mitm-simple-route-' + row.name.replace(/_/g, '-'),
					class: 'cbi-input-checkbox',
					type: 'checkbox',
					checked: checked ? '' : null,
					style: 'appearance:auto!important;-webkit-appearance:auto!important;' +
						'width:1.15rem!important;height:1.15rem!important;margin:0;' +
						'display:block;accent-color:#5e72e4;cursor:pointer',
					change: onChange
				})),
				E('td', { class: 'td left' }, [
					E('strong', {}, row.label),
					E('small', { style: 'display:block;margin-top:.2rem;opacity:.75' }, row.domains)
				]),
				E('td', { class: 'td left' }, row.destination),
				E('td', { class: 'td left' }, statusPill(status.label, status.tone)),
				E('td', { class: 'td left' }, row.name)
			]));
		});

		return E('div', { style: 'overflow:auto;margin:1rem 0' }, E('table', { class: 'table' }, [
			E('thead', {}, E('tr', { class: 'tr table-titles' }, [
				E('th', { class: 'th left' }, _('Use')),
				E('th', { class: 'th left' }, _('Traffic group')),
				E('th', { class: 'th left' }, _('Destination')),
				E('th', { class: 'th left' }, _('Status')),
				E('th', { class: 'th left' }, _('PassWall2 rule'))
			])),
			E('tbody', {}, body)
		]));
	},

	renderSimple: function(setup, status, certificates, passwall, page) {
		var current = slotData(certificates, 'current');
		var certificateReady = setup.certificate && setup.certificate.ready === true;
		var candidateAttention = setup.certificate && setup.certificate.candidate_requires_attention === true;
		var certificateAttention = setup.certificate && setup.certificate.requires_attention === true;
		var passwallState = setup.passwall2 || {};
		var routingState = passwall.routing_state || setup.routing || {};
		var routingMeta = setup.routing || {};
		var basicRoutingStatus = state.deriveBasicRoutingStatus(routingMeta, passwall.routing_state);
		var shunts = optionList(passwall.shunt_nodes || passwall.shunts);
		var vpns = optionList(passwall.vpn_nodes || passwall.vpns);
		var selectedVpn = passwall.selected_vpn || (vpns[0] && vpns[0].id);
		var canReviewRouting = passwallState.compatible === true && passwall.writable === true &&
			routingMeta.recovery_pending !== true && passwall.recovery_pending !== true &&
			shunts.length > 0 && vpns.length > 0;
		var setupBlocked = candidateAttention || certificateAttention;
		var setupComplete = setup.ready === true && setup.service && setup.service.boot_enabled === true;
		var pageStyle = function(name) { return page === name ? '' : 'display:none'; };

		return E('div', { id: 'xray-mitm-simple' }, [
			E('div', { id: 'xray-mitm-simple-basic', class: 'cbi-section cbi-tabcontainer',
				'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'overview', style: pageStyle('overview') }, [
				E('h3', {}, _('Basic settings')),
				this.overviewStatusStrip(status, certificates, passwall),
				this.simpleStateRow(_('MITM application'), _('Installed'), 'good', _('The router backend is connected.')),
				this.simpleStateRow(_('PassWall2'), passwallState.installed === true ? _('Detected') : _('Not detected'),
					passwallState.installed === true ? 'good' : 'warn'),
				this.simpleStateRow(_('Routing profile'), passwallState.shunt_available === true ? _('Available') : _('Missing'),
					passwallState.shunt_available === true ? 'good' : 'warn'),
				this.simpleStateRow(_('VPN connection'), passwallState.vpn_available === true ? _('Available') : _('Missing'),
					passwallState.vpn_available === true ? 'good' : 'warn')
			]),
			E('div', { id: 'xray-mitm-simple-certificate', class: 'cbi-section cbi-tabcontainer',
				'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'setup', style: pageStyle('setup') }, [
				E('h3', {}, _('Setup')),
				this.simpleStateRow(_('Router configuration'), setup.config && setup.config.present === true ? _('Ready') : _('Needed'),
					setup.config && setup.config.present === true ? 'good' : 'warn'),
				this.simpleStateRow(_('Certificate'), certificateReady ? _('Ready') : (setupBlocked ? _('Needs attention') : _('Needed')),
					certificateReady ? 'good' : 'warn'),
				this.simpleStateRow(_('MITM service'), status.running === true ? _('Running') : _('Stopped'),
					status.running === true ? 'good' : 'warn'),
				setupBlocked ? E('div', { class: 'alert-message warning' }, candidateAttention ? _(
					'A certificate candidate already exists. Open Advanced settings to review it before continuing.'
				) : _('Existing certificate files need attention. Open Advanced settings to review them.')) : '',
				E('p', {}, E('button', {
					class: 'btn cbi-button-positive',
					disabled: setupComplete || setupBlocked ? '' : null,
					click: ui.createHandlerFn(this, 'setupRecommended')
				}, setupComplete ? _('Setup complete') : _('Set up automatically')))
			]),
			E('div', { class: 'cbi-section cbi-tabcontainer',
				'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'setup', style: pageStyle('setup') }, [
				E('h3', {}, _('Certificate for your device')),
				E('p', {}, _('Devices using MITM websites must trust this public certificate. The private key stays on the router.')),
				certificateReady && slotPresent(current) ? E('p', {}, E('button', {
					class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'downloadCurrentCertificate')
				}, _('Download public certificate'))) : E('div', { class: 'alert-message notice' },
					certificateReady ? _('Adopt the existing legacy certificate in Advanced settings before downloading it here.') : _(
						'Complete automatic setup before downloading the certificate.'
					)),
				E('details', { style: 'margin-top:.8rem' }, [
					E('summary', { style: 'cursor:pointer;font-weight:600' }, _('How to install it on your device')),
					E('ul', {}, [
						E('li', {}, _('macOS: add the certificate to the System keychain and set it to Always Trust.')),
						E('li', {}, _('Windows: open the certificate, choose Install Certificate, and place it in Trusted Root Certification Authorities.')),
						E('li', {}, _('Android: open Security settings, choose Install a certificate, then install it as a CA certificate.')),
						E('li', {}, _('iPhone or iPad: install the downloaded profile, then enable full trust in Certificate Trust Settings.'))
					])
				])
			]),
			E('div', { id: 'xray-mitm-simple-routing', class: 'cbi-section cbi-tabcontainer',
				'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'routing', style: pageStyle('routing') }, [
				E('h3', {}, _('Routing rules')),
				E('p', {}, _('Choose the service groups to use. The table shows the destination that will be assigned in PassWall2.')),
				passwallState.installed !== true ? E('div', { class: 'alert-message warning' }, _(
					'PassWall2 was not detected. MITM can still run, but automatic routing requires PassWall2.'
				)) : '',
				passwallState.installed === true && passwallState.shunt_available !== true ? E('div', { class: 'alert-message warning' }, _(
					'Create or select a shunt routing profile in PassWall2, then return here.'
				)) : '',
				passwallState.installed === true && passwallState.vpn_available !== true ? E('div', { class: 'alert-message warning' }, _(
					'No usable VPN connection was found. Add and test a VPN node in PassWall2, then return here.'
				)) : '',
				canReviewRouting ? E('div', {}, [
					E('div', { class: 'alert-message notice' }, _(
						'Automatic setup prepares only the MITM service. It never edits PassWall2 routing; these checkboxes change routing only after you preview and apply it.'
					)),
					E('p', {}, _('New to PassWall2? Select the recommended choices, preview the result, then apply it.')),
					E('p', {}, E('button', {
						class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'useSimpleRecommendedRouting')
					}, _('Use recommended choices'))),
					this.simpleRoutingSummary(),
					E('details', { style: 'margin:1rem 0' }, [
						E('summary', { style: 'cursor:pointer;font-weight:600' }, _('Customize routing')),
						this.simpleRoutingTable(routingState, passwall)
					]),
					E('label', { for: 'xray-mitm-simple-vpn', style: 'display:block;font-weight:600;margin-bottom:.35rem' }, _('VPN destination for selected overrides')),
					selectControl('xray-mitm-simple-vpn', vpns, selectedVpn, function() {
						dom.content(document.getElementById('xray-mitm-simple-routing-preview'), '');
					}),
					E('p', {}, E('button', {
						class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'reviewRecommendedRouting')
					}, _('Preview selected routing'))),
					E('div', { id: 'xray-mitm-simple-routing-preview', 'aria-live': 'polite' })
				]) : ''
			]),
			E('div', { id: 'xray-mitm-simple-status', class: 'cbi-section cbi-tabcontainer',
				'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'status', style: pageStyle('status') }, [
				E('h3', {}, _('Status')),
				this.simpleStateRow(_('MITM'), status.running === true ? _('Running') : _('Stopped'), status.running === true ? 'good' : 'warn'),
				this.simpleStateRow(_('Routing'), basicRoutingStatus.kind === 'recommended' ? _('Recommended') :
					(basicRoutingStatus.kind === 'custom' ? _('Custom') : _('Not configured')),
					basicRoutingStatus.tone),
				this.simpleStateRow(_('PassWall2'), passwallState.compatible === true ? _('Working') : _('Needs attention'),
					passwallState.compatible === true ? 'good' : 'warn'),
				E('div', {
					style: 'display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;' +
						'padding:.7rem 0;border-bottom:1px solid var(--border-color-low,#ddd)'
				}, [ E('strong', {}, _('Health check')), E('span', { id: 'xray-mitm-simple-health' }, statusPill(_('Not run'), 'muted')) ]),
				E('p', {}, E('button', {
					class: 'btn cbi-button-action', disabled: status.running === true ? null : '',
					click: ui.createHandlerFn(this, 'runHealth')
				}, _('Run check')))
			])
		]);
	},

	renderSetupGuide: function(status, certificates, passwall) {
		var current = slotData(certificates, 'current');
		var routing = (passwall && passwall.routing_state) || {};
		var progress = state.setupProgress(status, certificates, { routing_state: routing });
		var routingReady = progress.routingReady;
		var firstTime = progress.firstTime;
		var steps = [
			{
				number: '1',
				title: _('Prepare the service'),
				done: status.configured === true,
				description: status.configured === true ? _('Configuration is ready.') : _('Install the packaged configuration below.')
			},
			{
				number: '2',
				title: _('Prepare the certificate'),
				done: slotPresent(current),
				description: slotPresent(current) ? _('A public certificate is ready to download.') : _('Create or adopt a certificate below.')
			},
			{
				number: '3',
				title: _('Start MITM'),
				done: status.running === true,
				description: status.running === true ? _('The local service is running.') : _('Start the service before enabling MITM-Compatible Services.')
			},
			{
				number: '4',
				title: _('Choose routing'),
				done: routingReady,
				description: routingReady ? _('PassWall2 routing choices are saved.') : _('Use the easy routing assistant below.')
			}
		];

		return E('div', { class: 'cbi-section' }, [
			E('h3', {}, firstTime ? _('First-time setup') : _('System overview')),
			E('p', {}, firstTime ?
				_('Complete these steps once, in order. Green items are already ready.') :
				_('Updates preserve your configuration and certificate. These cards show the current state; complete only items that are not ready.')),
			this.overviewStatusStrip(status, certificates, passwall),
			E('div', {
				class: 'xray-mitm-step-strip',
				style: 'display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;' +
					'align-items:stretch;gap:.7rem;width:100%;box-sizing:border-box;' +
					'padding:.75rem;margin:1rem 0;border:1px solid var(--border-color-medium,#ccc);' +
					'border-radius:.35rem;background:rgba(128,128,128,.12)'
			}, steps.map(function(step) {
					return E('div', {
						style: 'display:flex;flex-direction:column;justify-content:center;width:100%;min-height:5.25rem;' +
							'padding:.75rem .9rem;border:1px solid var(--border-color-medium,#ccc);' +
							'border-radius:.35rem;background:rgba(0,0,0,.12);box-sizing:border-box'
					}, [
						E('div', { style: 'display:flex;align-items:center;gap:.55rem;margin-bottom:.45rem' }, [
							statusPill(step.done ? '✓' : (firstTime ? step.number : '!'), step.done ? 'good' : 'warn'),
							E('strong', {}, step.title)
						]),
						E('small', { style: 'line-height:1.45;opacity:.8' }, step.description)
					]);
				})
			)
		]);
	},

	renderService: function(status) {
		var running = status.running === true ? _('Running') :
			(status.running === false ? _('Stopped') : _('Unknown'));
		var enabled = status.enabled === true ? _('Enabled') :
			(status.enabled === false ? _('Disabled') : _('Unknown'));
		var configured = status.configured === true ? _('Ready') :
			(status.configured === false ? _('Not provisioned') : _('Unknown'));

		return E('div', { class: 'cbi-section' }, [
			E('h3', {}, _('MITM service')),
			E('p', {}, _(
				'This local service handles websites assigned to “MITM-Compatible Services” in the routing assistant below.'
			)),
			status.running === false ? E('div', { class: 'alert-message warning' }, _(
				'The service is stopped. Existing MITM-Compatible Services routes will not work until it is started.'
			)) : '',
			E('table', { class: 'table' }, [
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left', width: '35%' }, _('State')), E('td', { class: 'td left' }, running) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Start at boot')), E('td', { class: 'td left' }, enabled) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Configuration')), E('td', { class: 'td left' }, configured) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Routing connection')), E('td', { class: 'td left' }, 'Local only (127.0.0.1:10808)') ])
			]),
			E('p', { style: 'display:flex;gap:.5rem;flex-wrap:wrap' }, [
				status.running === true ? E('button', { class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'serviceAction', 'restart') }, _('Restart service')) :
					E('button', { class: 'btn cbi-button-positive', click: ui.createHandlerFn(this, 'serviceAction', 'start') }, _('Start service')),
				status.running === true ? E('button', { class: 'btn cbi-button-negative', click: ui.createHandlerFn(this, 'serviceAction', 'stop') }, _('Stop service')) : '',
				status.enabled === true ? E('button', { class: 'btn', click: ui.createHandlerFn(this, 'serviceAction', 'disable') }, _('Disable automatic start')) :
					E('button', { class: 'btn cbi-button-positive', click: ui.createHandlerFn(this, 'serviceAction', 'enable') }, _('Start automatically after reboot'))
			]),
			status.configured === false ? E('p', {}, E('button', {
				class: 'btn cbi-button-action',
				click: ui.createHandlerFn(this, 'installConfig')
			}, _('Install packaged default configuration'))) : '',
			E('p', {}, E('button', {
				class: 'btn cbi-button-action',
				disabled: status.running === true ? null : '',
				click: ui.createHandlerFn(this, 'runHealth')
			}, _('Check that MITM is working'))),
			E('pre', {
				id: 'xray-mitm-health-output',
				style: 'white-space:pre-wrap; max-height:28em; overflow:auto'
			}, _('Health check has not been run.'))
		]);
	},

	renderCertificates: function(certificates) {
		var candidate = slotData(certificates, 'candidate');
		var previous = slotData(certificates, 'previous');
		var current = slotData(certificates, 'current');
		var secureImport = window.location.protocol === 'https:' && window.isSecureContext !== false;
		var statusReady = certificates.ok === true;

		return E('div', { class: 'cbi-section' }, [
			E('h3', {}, _('Certificate for your devices')),
			E('p', {}, _(
				'Download and trust the public certificate on devices that will use Google through MITM. The private key always remains protected on this router.'
			)),
			!statusReady ? E('div', { class: 'alert-message danger' },
				textNode(certificates.error, _('Unable to read certificate status.'))) : '',
			certificates.recovery_pending === true ? E('div', { class: 'alert-message warning' }, _(
				'An interrupted certificate change is awaiting recovery. Do not download or trust a CA until a service or certificate action has recovered it.'
			)) : '',
			certificates.invalid_pair === true ? E('div', { class: 'alert-message danger' }, _(
				'The legacy certificate files are incomplete or unsafe. Repair them through SSH before activating another CA.'
			)) : '',
			E('table', { class: 'table' }, [
				E('tr', { class: 'tr table-titles' }, [
					E('th', { class: 'th left' }, _('Slot')),
					E('th', { class: 'th left' }, _('Name')),
					E('th', { class: 'th left' }, _('SHA-256 fingerprint')),
					E('th', { class: 'th left' }, _('Expires')),
					E('th', { class: 'th left' }, _('Public certificate'))
				])
			].concat(certificateRows(certificates))),
			E('p', {}, _(
				'Before trusting a downloaded CA, compare its SHA-256 fingerprint with the value read directly from the router over SSH.'
			)),
			E('h4', {}, _('Generate a candidate on the router')),
			E('div', { class: 'cbi-value' }, [
				E('label', { class: 'cbi-value-title', for: 'xray-mitm-ca-cn' }, _('Common name')),
				E('div', { class: 'cbi-value-field' }, E('input', {
					id: 'xray-mitm-ca-cn', class: 'cbi-input-text', value: 'MITM-DomainFronting', maxlength: 64
				}))
			]),
			E('div', { class: 'cbi-value' }, [
				E('label', { class: 'cbi-value-title', for: 'xray-mitm-ca-days' }, _('Validity in days')),
				E('div', { class: 'cbi-value-field' }, E('input', {
					id: 'xray-mitm-ca-days', class: 'cbi-input-text', type: 'number', min: 365, max: 3650, value: 3650
				}))
			]),
			E('p', {}, E('button', {
				class: 'btn cbi-button-action',
				disabled: !statusReady || slotPresent(candidate) ? '' : null,
				click: ui.createHandlerFn(this, 'generateCandidate')
			}, _('Generate candidate'))),
			slotPresent(candidate) ? E('p', {}, [
				E('button', { class: 'btn cbi-button-positive', click: ui.createHandlerFn(this, 'activateCandidate') }, _('Activate candidate')), ' ',
				E('button', { class: 'btn cbi-button-negative', click: ui.createHandlerFn(this, 'discardCandidate') }, _('Discard candidate'))
			]) : '',
			slotPresent(previous) && slotPresent(current) ? E('p', {}, E('button', {
				class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'rollbackCertificate')
			}, _('Restore previous CA'))) : '',
				(certificates.legacy_pair === true || certificates.legacyPairPresent === true) ? E('p', {}, E('button', {
				class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'adoptLegacyCertificate')
			}, _('Adopt existing certificate pair'))) : '',
			E('h4', {}, _('Import an existing pair as candidate')),
			E('p', {}, secureImport ? _(
				'Choose one public CA certificate and its matching unencrypted private key. Prefer router-generated keys unless you are deliberately migrating an existing CA.'
			) : _(
				'Private-key import is disabled on HTTP. Enable HTTPS for LuCI or import through SSH.'
			)),
			E('div', { class: 'cbi-value' }, [
				E('label', { class: 'cbi-value-title', for: 'xray-mitm-import-cert' }, _('Public CA certificate')),
				E('div', { class: 'cbi-value-field' }, E('input', {
					id: 'xray-mitm-import-cert', type: 'file', accept: '.crt,.pem,application/x-pem-file',
					disabled: secureImport && statusReady ? null : ''
				}))
			]),
			E('div', { class: 'cbi-value' }, [
				E('label', { class: 'cbi-value-title', for: 'xray-mitm-import-key' }, _('Private key')),
				E('div', { class: 'cbi-value-field' }, E('input', {
					id: 'xray-mitm-import-key', type: 'file', accept: '.key,.pem,application/x-pem-file',
					disabled: secureImport && statusReady ? null : ''
				}))
			]),
			E('p', {}, E('button', {
				class: 'btn cbi-button-action', disabled: secureImport && statusReady ? null : '',
				click: ui.createHandlerFn(this, 'importCandidate')
			}, _('Import candidate pair')))
		]);
	},

	renderRouting: function(inspect) {
		var shunts = optionList(inspect.shunt_nodes || inspect.shunts);
		var vpns = optionList(inspect.vpn_nodes || inspect.vpns);
		var selection = state.passwallSelection(inspect);
		var capabilities = inspect.capabilities || {};
		var recoveryPending = inspect.recovery_pending === true;
		var compatible = selection.compatible;
		var canPlan = !recoveryPending && compatible && inspect.writable === true && capabilities.plan !== false;
		var canRollback = !recoveryPending && capabilities.rollback !== false && !!this.rollbackTransaction;
		var selectedShunt = selection.selectedShunt;
		var selectedVpn = selection.selectedVpn;
		var routingState = inspect.routing_state || {};
		var ruleSources = inspect.rule_sources || {};
		var mitmNode = inspect.mitm_node || {};
		var hasExistingRules = Object.keys(ruleSources).some(function(name) {
			return ruleSources[name] === 'existing';
		});
		var mitmRunning = this.status && this.status.running === true;
		var readinessTone = compatible && !recoveryPending && inspect.pending_changes !== true ? 'good' : 'warn';
		var selectionChanged = L.bind(this.routingSelectionChanged, this);

		return E('div', { class: 'cbi-section' }, [
			E('h3', {}, _('PassWall2 routing')),
			E('p', {}, _(
				'Use the familiar PassWall2 rule style: choose a destination for each service group, review the exact changes, then apply them together.'
			)),
			E('div', { style: 'display:flex;align-items:center;justify-content:space-between;gap:1rem;' +
				'padding:.85rem 1rem;margin:1rem 0;border:1px solid var(--border-color-medium,#ccc);' +
				'border-radius:.45rem;background:rgba(94,114,228,.08);flex-wrap:wrap' }, [
				E('div', {}, [
					E('strong', { style: 'display:block' }, _('Rule assignment')),
					E('small', { style: 'display:block;margin-top:.2rem;opacity:.78' }, _('Changes remain staged until you apply the reviewed preview.'))
				]),
				statusPill(recoveryPending ? _('Recovery required') : (canPlan ? _('Ready to review') : _('Needs attention')),
					recoveryPending ? 'warn' : (canPlan ? 'good' : 'warn'))
			]),
			E('div', { style: 'display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.7rem;margin:1rem 0' }, [
				E('div', { style: 'padding:.85rem 1rem;border:1px solid var(--border-color-medium,#ccc);border-radius:.45rem' }, [
					E('small', { style: 'display:block;opacity:.75;margin-bottom:.3rem' }, _('PassWall2')), statusPill(
						compatible ? _('Ready') : _('Needs attention'), readinessTone)
				]),
				E('div', { style: 'padding:.85rem 1rem;border:1px solid var(--border-color-medium,#ccc);border-radius:.45rem' }, [
					E('small', { style: 'display:block;opacity:.75;margin-bottom:.3rem' }, _('MITM service')), statusPill(
						mitmRunning ? _('Running') : _('Stopped'), mitmRunning ? 'good' : 'warn')
				]),
				E('div', { style: 'padding:.85rem 1rem;border:1px solid var(--border-color-medium,#ccc);border-radius:.45rem' }, [
					E('small', { style: 'display:block;opacity:.75;margin-bottom:.3rem' }, _('Local SOCKS node')), statusPill(
						mitmNode.status === 'ready' ? _('Found') : _('Created when needed'),
						mitmNode.status === 'ready' ? 'good' : 'info')
				])
			]),
			recoveryPending ? E('div', { class: 'alert-message danger' }, [
				E('p', {}, textNode(inspect.error, _('An interrupted routing transaction must be recovered before inspection or new changes.'))),
				E('button', {
					class: 'btn cbi-button-negative',
					disabled: capabilities.recover === false ? '' : null,
					click: ui.createHandlerFn(this, 'recoverRouting')
				}, _('Recover previous PassWall2 file'))
			]) : '',
			!compatible && !recoveryPending ? E('div', { class: 'alert-message warning' },
				textNode(inspect.message || inspect.error, _('Create or select a PassWall2 shunt and add at least one working VPN node, then return to this page.'))) : '',
			compatible && !canPlan ? E('div', { class: 'alert-message warning' }, _(
				'Save or revert pending PassWall2 changes before creating a routing preview.'
			)) : '',
			compatible ? E('div', {}, [
				E('h4', {}, _('1. Choose your existing connections')),
				E('p', { style: 'opacity:.82' }, _(
					'The assistant will not create or edit VPN credentials. Choose the shunt that is active in PassWall2 and the VPN connection that already works.'
				)),
				E('div', { class: 'cbi-value' }, [
					E('label', { class: 'cbi-value-title', for: 'xray-mitm-route-shunt-node' }, _('Main routing profile')),
					E('div', { class: 'cbi-value-field' }, selectControl('xray-mitm-route-shunt-node', shunts, selectedShunt, selectionChanged))
				]),
				E('div', { class: 'cbi-value' }, [
					E('label', { class: 'cbi-value-title', for: 'xray-mitm-route-vpn-node' }, _('Working VPN connection')),
					E('div', { class: 'cbi-value-field' }, selectControl('xray-mitm-route-vpn-node', vpns, selectedVpn, selectionChanged))
				]),
				E('h4', {}, _('2. Choose what should happen')),
				E('p', {}, [
					E('button', { class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'useRecommendedRouting') }, _('Use recommended choices')), ' ',
					E('button', { class: 'btn', click: ui.createHandlerFn(this, 'restoreCurrentRouting') }, _('Restore saved choices'))
				]),
				hasExistingRules ? E('div', { class: 'alert-message notice' }, _(
					'Recognized older rules were found. Their definitions will be preserved while this assistant replaces their selected-shunt assignments with the three managed rules.'
				)) : '',
				!mitmRunning ? E('div', { class: 'alert-message warning' }, _(
					'MITM Domain Fronting is stopped. You can review choices, but a preview containing MITM-Compatible Services cannot be applied until the service is running.'
				)) : '',
				routingRuleCard('1', _('VPN Overrides'), _('Destination: selected VPN connection'), _(
					'Put only services that need the normal VPN in this higher-priority rule.'
				), [
					{ id: 'xray-mitm-route-gemini', label: _('Gemini app and API'), description: 'gemini.google.com, generativelanguage.googleapis.com', checked: routingState.gemini === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-android-check', label: _('Android internet checks'), description: 'connectivitycheck.gstatic.com, connectivitycheck.android.com, clients3.google.com', checked: routingState.android_check === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-youtube-control', label: _('YouTube sign-in and controls'), description: _('YouTube UI/API domains; googlevideo.com stays outside this VPN override and uses MITM only when the optional Google route is enabled.'), checked: routingState.youtube_control === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-google-play', label: _('Google Play and Android services'), description: _('Google Play, Android authentication, check-in, and download endpoints. These use the selected VPN instead of MITM.'), checked: routingState.google_play === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-accounts-google', label: _('Google Account sign-in'), description: 'accounts.google.com', checked: routingState.accounts_google === true, onChange: selectionChanged }
				], ruleSources.vpn_overrides),
					routingRuleCard('2', _('MITM-Compatible Services'), _('Destination: local SOCKS 127.0.0.1:10808'), _(
					'The assistant reuses or creates the localhost SOCKS node. Enable only service groups you have tested on your devices.'
				), [
					{ id: 'xray-mitm-route-google-mitm', label: _('Google Drive and YouTube video'), description: _('Selected Drive API/upload and googlevideo.com domains only, not all Google services. Google Play and Android services stay on the VPN override.'), checked: routingState.google_mitm === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-google-meet', label: _('Google Meet web and signaling'), description: _('Meet web and signaling hostnames; audio/video media may use UDP or separate media IPs, so test a real call before relying on MITM.'), checked: routingState.google_meet === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-meta-mitm', label: _('Meta websites'), description: _('geosite:meta (optional; test before relying on native apps)'), checked: routingState.meta_mitm === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-fastly-mitm', label: _('Fastly-backed websites'), description: _('Fastly, Reddit, CNN, and BuzzFeed groups from the packaged Patterniha configuration'), checked: routingState.fastly_mitm === true, onChange: selectionChanged }
				], ruleSources.mitm_services),
				routingRuleCard('3', _('Regional Direct Access'), _('Destination: direct connection'), _(
					'Bypass VPN and MITM for selected local regions.'
				), [
					{ id: 'xray-mitm-route-iran-direct', label: _('Iranian websites and IP addresses'), description: 'geosite:ir, geoip:ir', checked: routingState.iran_direct === true, onChange: selectionChanged }
				], ruleSources.regional_direct),
				E('details', { style: 'margin:1rem 0;padding:.2rem 0' }, [
					E('summary', { style: 'cursor:pointer;font-weight:600;padding:.6rem 0' }, _('Advanced routing settings')),
					simpleCheck('xray-mitm-route-set-default-vpn', _('Make this VPN the fallback route'), _('Changes the shunt default for traffic that does not match a rule.'), routingState.set_default_vpn === true, selectionChanged),
					simpleCheck('xray-mitm-route-set-localhost-proxy-zero', _('Protect the local MITM connection from recapture'), _('Recommended. Sets localhost_proxy=0 so PassWall2 does not capture the local SOCKS connection again.'), routingState.set_localhost_proxy_zero === true, selectionChanged)
				]),
				E('h4', {}, _('3. Review and apply')),
				E('p', { style: 'opacity:.82' }, _(
					'Review builds a private temporary copy first. Nothing is changed until you apply that exact preview. A rollback copy is kept. Applying may briefly interrupt traffic; keep this page open while PassWall2 restarts and confirms the changes.'
				)),
				E('p', { style: 'display:flex;gap:.5rem;flex-wrap:wrap' }, [
					E('button', { class: 'btn cbi-button-action', disabled: canPlan ? null : '', click: ui.createHandlerFn(this, 'planRouting') }, _('Review setup')), ' ',
					E('button', { id: 'xray-mitm-routing-apply', class: 'btn cbi-button-positive', disabled: '', click: ui.createHandlerFn(this, 'applyRouting') }, _('Apply reviewed setup')), ' ',
					E('button', { id: 'xray-mitm-routing-rollback', class: 'btn cbi-button-negative', disabled: canRollback ? null : '', click: ui.createHandlerFn(this, 'rollbackRouting') }, _('Rollback last transaction'))
				]),
				E('div', { id: 'xray-mitm-routing-preview', 'aria-live': 'polite' })
			]) : ''
		]);
	},

	render: function(data) {
		this.setup = data[0] || {};
		this.status = data[1] || {};
		this.certificates = data[2] || {};
		this.passwall = data[3] || {};
		this.routingBusy = false;
		this.routingBusyTimer = null;
		this.appVersion = text(this.setup.app_version || this.setup.version, PROJECT_VERSION)
			.replace(/^v/i, '');
		this.planToken = null;
		this.rollbackTransaction = this.passwall.rollback_transaction || null;

		return E('div', {}, [
			E('h2', { style: 'display:flex;align-items:center;gap:.65rem;flex-wrap:wrap' }, [
				_('MITM Domain Fronting'),
				E('span', {
					class: 'xray-mitm-version-badge',
					title: _('Application version'),
					style: 'display:inline-block;padding:.18rem .55rem;border:1px solid var(--border-color-medium,#ccc);' +
						'border-radius:999px;font-size:.55em;font-weight:600;line-height:1.2;opacity:.82'
				}, 'v' + this.appVersion)
			]),
			E('p', {}, _(
				'Prepare the MITM service, download the public certificate, and configure safe PassWall2 routing.'
			)),
			this.pageNavigation(),
			this.setup.ok === false ? E('div', { class: 'alert-message danger' }, textNode(this.setup.error, _('Unable to read setup status.'))) : '',
			this.renderSimple(this.setup, this.status, this.certificates, this.passwall, 'overview'),
			E('div', { id: 'xray-mitm-advanced', style: 'display:none' }, [
				E('div', { class: 'alert-message notice' }, _(
					'Advanced settings expose manual service, certificate, transaction, and routing controls.'
				)),
				E('div', { class: 'cbi-tabcontainer', 'data-dashboard-panel-mode': 'advanced',
					'data-dashboard-panel-page': 'overview', style: 'display:none' },
				this.renderSetupGuide(this.status, this.certificates, this.passwall)),
				E('div', { class: 'cbi-tabcontainer', 'data-dashboard-panel-mode': 'advanced',
					'data-dashboard-panel-page': 'service', style: 'display:none' }, [
					this.status.ok === false ? E('div', { class: 'alert-message danger' }, textNode(this.status.error, _('Unable to read service status.'))) : '',
					this.renderService(this.status)
				]),
				E('div', { class: 'cbi-tabcontainer', 'data-dashboard-panel-mode': 'advanced',
					'data-dashboard-panel-page': 'certificates', style: 'display:none' },
				this.renderCertificates(this.certificates)),
				E('div', { class: 'cbi-tabcontainer', 'data-dashboard-panel-mode': 'advanced',
					'data-dashboard-panel-page': 'routing', style: 'display:none' },
				this.renderRouting(this.passwall))
			]),
			E('div', { class: 'alert-message warning' }, _(
				'Trust the public CA only on devices you control. Never copy, publish, or download the router private CA key.'
			))
		]);
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
