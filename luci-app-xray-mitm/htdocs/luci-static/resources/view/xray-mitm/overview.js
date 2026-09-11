'use strict';
'require view';
'require rpc';
'require ui';
'require dom';
'require xray-mitm.state as state';

/* Keep this fallback synchronized with xray-mitm/Makefile PKG_VERSION. */
var PROJECT_VERSION = '0.4.2';

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

var routingParams = [
	'shunt_node', 'vpn_node', 'gemini', 'android_check',
	'youtube_control', 'google_mitm', 'meta_mitm', 'fastly_mitm', 'iran_direct', 'accounts_google',
	'set_default_vpn', 'set_localhost_proxy_zero'
];

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

var callRollbackPassWall2 = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'rollbackPassWall2',
	params: [ 'transaction' ],
	expect: { '': {} }
});

function text(value, fallback) {
	if (value === null || value === undefined || value === '')
		return fallback || _('Unknown');

	return String(value);
}

function textNode(value, fallback) {
	return document.createTextNode(text(value, fallback));
}

function yesNo(value) {
	if (value === true)
		return _('Yes');

	if (value === false)
		return _('No');

	return _('Unknown');
}

function assertOk(result) {
	if (!result || result.ok === false)
		throw new Error(result && (result.message || result.error) ?
			(result.message || result.error) : _('Operation failed.'));

	return result;
}

function notification(message, type) {
	ui.addNotification(null, E('p', {}, textNode(message, _('Operation completed.'))), type || 'info');
}

function setBusy(button, busy) {
	if (button)
		button.disabled = busy;
}

function readSelectedFile(input, maximum) {
	return new Promise(function(resolve, reject) {
		var file = input && input.files && input.files[0];

		if (!file) {
			reject(new Error(_('Choose a file first.')));
			return;
		}

		if (file.size > maximum) {
			reject(new Error(_('The selected file is too large.')));
			return;
		}

		var reader = new FileReader();
		reader.onerror = function() {
			reject(new Error(_('The selected file could not be read.')));
		};
		reader.onload = function() {
			resolve(String(reader.result || ''));
		};
		reader.readAsText(file);
	});
}

function slotData(data, name) {
	if (!data)
		return {};

	if (data.slots && data.slots[name])
		return data.slots[name];

	return data[name] || {};
}

function slotPresent(slot) {
	return slot && (slot.present === true || !!slot.fingerprint);
}

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

function decodeRemarks(item) {
	if (!item || !item.remarks_b64)
		return item && (item.remarks || item.label) || '';

	try {
		var bytes = Uint8Array.from(atob(item.remarks_b64), function(character) {
			return character.charCodeAt(0);
		});
		return new TextDecoder('utf-8').decode(bytes);
	}
	catch (error) {
		return '';
	}
}

function optionList(items) {
	if (!Array.isArray(items))
		return [];

	return items.map(function(item) {
		if (typeof item === 'string')
			return { id: item, label: item };

		var id = item.id || item.name || item.section;
		var details = [ item.group, item.protocol, item.type ].filter(Boolean).join(' · ');
		var remarks = decodeRemarks(item);
		return {
			id: id,
			group: item.group || '',
			label: (remarks || _('Unnamed node') + ' [' + id + ']') + (details ? ' — ' + details : '')
		};
	}).filter(function(item) { return !!item.id; });
}

function selectControl(id, items, selected, onChange) {
	var select = E('select', { id: id, class: 'cbi-input-select' });
	if (onChange)
		select.addEventListener('change', onChange);

	var groups = {};
	items.forEach(function(item) {
		var group = item.group || '';
		if (!groups[group])
			groups[group] = [];
		groups[group].push(item);
	});

	Object.keys(groups).forEach(function(group) {
		var target = group ? E('optgroup', { label: group }) : select;
		groups[group].forEach(function(item) {
			target.appendChild(E('option', {
				value: item.id,
				selected: item.id === selected ? '' : null
			}, textNode(item.label)));
		});
		if (target !== select)
			select.appendChild(target);
	});

	return select;
}

function statusPill(label, tone) {
	var colors = {
		good: [ '#e7f5e7', '#246b2d' ],
		info: [ '#e8f1fb', '#245b91' ],
		muted: [ '#eeeeee', '#555555' ],
		warn: [ '#fff3cd', '#7a5700' ]
	};
	var color = colors[tone] || colors.muted;

	return E('span', {
		style: 'display:inline-block;padding:.18rem .55rem;border-radius:999px;' +
			'font-size:.82em;font-weight:600;background:' + color[0] + ';color:' + color[1]
	}, label);
}

function routeStatus(source, active) {
	var result = state.routeStatus(source, active);
	var labels = {
		active: _('Active now'),
		existing: _('Existing rule found'),
		managed: _('Ready but disabled'),
		new: _('Will be created')
	};

	return { label: labels[result.kind] || labels.new, tone: result.tone };
}

function simpleCheck(id, label, description, checked, onChange) {
	var checkbox = E('input', {
		id: id,
		class: 'cbi-input-checkbox xray-mitm-choice-input',
		type: 'checkbox',
		checked: checked ? '' : null,
		style: 'appearance:auto!important;-webkit-appearance:auto!important;' +
			'position:static!important;float:none!important;display:block!important;' +
			'width:1.25rem!important;height:1.25rem!important;' +
			'margin:0!important;padding:0!important;flex:0 0 1.25rem;' +
			'accent-color:#5e72e4;cursor:pointer',
		change: onChange
	});

	return E('label', {
		class: 'xray-mitm-choice-row',
		for: id,
		style: 'display:grid;grid-template-columns:2rem minmax(0,1fr);align-items:start;' +
			'column-gap:.65rem;margin:0;padding:.7rem .75rem;' +
			'border-top:1px solid var(--border-color-low,#ddd);cursor:pointer;' +
			'background:rgba(255,255,255,.015);min-height:3.2rem;box-sizing:border-box'
	}, [
		E('span', { style: 'display:flex;align-items:flex-start;justify-content:center;padding-top:.05rem' }, checkbox),
		E('span', { style: 'display:block;min-width:0;line-height:1.35' }, [
			E('strong', {}, label),
			description ? E('small', { style: 'display:block;margin-top:.25rem;opacity:.78;line-height:1.35' }, description) : ''
		])
	]);
}

function routingRuleCard(number, title, destination, description, choices, source) {
	var active = choices.some(function(choice) { return choice.checked; });
	var status = routeStatus(source, active);
	return E('section', {
		style: 'margin:1rem 0;border:1px solid var(--border-color-medium,#ccc);' +
			'border-radius:.45rem;overflow:hidden;background:rgba(0,0,0,.08)'
	}, [
		E('div', { style: 'display:flex;align-items:center;justify-content:space-between;gap:1rem;' +
			'padding:.85rem 1rem;background:rgba(128,128,128,.14);border-bottom:1px solid var(--border-color-low,#ddd)' }, [
			E('div', { style: 'display:flex;align-items:center;gap:.65rem;min-width:0' }, [
				E('span', { style: 'display:inline-flex;align-items:center;justify-content:center;' +
					'width:1.65rem;height:1.65rem;border-radius:50%;font-weight:700;' +
					'background:#5e72e4;color:#fff;flex:0 0 auto' }, number),
				E('div', { style: 'min-width:0' }, [
					E('strong', { style: 'display:block' }, title),
					E('small', { style: 'display:block;margin-top:.2rem;opacity:.8' }, destination)
				])
			]),
			statusPill(status.label, status.tone)
		]),
		E('div', { style: 'padding:.75rem 1rem .35rem' }, [
			E('p', { style: 'margin:0;opacity:.85;line-height:1.45' }, description),
			E('small', { style: 'display:block;margin-top:.45rem;opacity:.7' }, _('Choose the rows to include in this PassWall2 rule.'))
		]),
		E('div', { style: 'margin:0 .35rem .35rem;border:1px solid var(--border-color-low,#ddd);border-radius:.3rem;overflow:hidden' }, choices.map(function(choice) {
			return simpleCheck(choice.id, choice.label, choice.description, choice.checked, choice.onChange);
		}))
	]);
}

function operationList(plan) {
	var operations = plan.operations || plan.changes || [];

	if (!Array.isArray(operations) || !operations.length)
		return E('p', {}, _('No configuration changes are required.'));

	return E('div', { style: 'display:grid;gap:.5rem;margin:.75rem 0' }, operations.map(function(operation) {
		if (typeof operation === 'string')
			return E('div', { style: 'padding:.65rem .8rem;border-left:4px solid #5e72e4;background:rgba(94,114,228,.08)' }, textNode(operation));

		return E('div', { style: 'padding:.65rem .8rem;border-left:4px solid #5e72e4;background:rgba(94,114,228,.08)' }, [
			E('strong', {}, textNode(operation.description || operation.action || operation.name)),
			operation.id ? E('small', { style: 'display:block;margin-top:.2rem;opacity:.75' },
				_('PassWall2 object: ') + operation.id) : ''
		]);
	}));
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
			{ name: 'certificates', label: _('Certificates') },
			{ name: 'routing', label: _('Routing') }
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
		var values = state.recommendedChoices();
		[ 'gemini', 'android_check', 'youtube_control', 'google_mitm', 'meta_mitm',
			'fastly_mitm', 'iran_direct', 'accounts_google' ].forEach(function(name) {
			var choice = document.getElementById('xray-mitm-simple-route-' + name.replace(/_/g, '-'));
			if (choice)
				values[name] = choice.checked;
		});
		values.shunt_node = shunt;
		values.vpn_node = vpn;
		setBusy(button, true);
		callPlanPassWall2.apply(null, state.routingArguments(values)).then(assertOk).then(L.bind(function(plan) {
			this.planToken = plan.no_change === true ? null : (plan.token || null);
			var blocked = plan.requires_mitm_running === true && this.status.running !== true;
			var children = [
				E('h4', {}, plan.no_change === true ? _('Recommended routing is already configured') : _('Ready to configure routing')),
				E('div', { style: 'display:grid;gap:.45rem;margin:.75rem 0' }, [
					this.simpleRouteRow(_('Google services'), _('MITM')),
					this.simpleRouteRow(_('Gemini'), _('Selected VPN')),
					this.simpleRouteRow(_('Iranian services'), _('Direct'))
				]),
				E('p', { style: 'opacity:.82' }, _('Unknown custom rules are preserved. The exact staged preview will be applied.'))
			];
			if (blocked)
				children.push(E('div', { class: 'alert-message warning' }, _('Start MITM before applying this routing setup.')));
			if (this.planToken && !blocked)
				children.push(E('button', {
					class: 'btn cbi-button-positive',
					click: ui.createHandlerFn(this, 'applyRouting')
				}, _('Apply recommended routing')));
			dom.content(output, children);
		}, this)).catch(function(error) {
			dom.content(output, E('div', { class: 'alert-message danger' }, textNode(error.message)));
		}).then(function() { setBusy(button, false); });
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

		callPlanPassWall2.apply(null, state.routingArguments(values)).then(assertOk).then(L.bind(function(plan) {
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
		if (!this.planToken || !window.confirm(_(
			'Apply exactly the previewed PassWall2 changes and restart PassWall2? A rollback snapshot will be kept.'
		)))
			return;

		this.runMutation(ev.currentTarget, callApplyPassWall2(this.planToken),
			_('PassWall2 routing changes applied.'), true).then(L.bind(function(result) {
			if (!result || !result.ok)
				return;

			this.rollbackTransaction = result.transaction || null;
			this.planToken = null;
			var apply = document.getElementById('xray-mitm-routing-apply');
			var rollback = document.getElementById('xray-mitm-routing-rollback');
			if (apply)
				apply.disabled = true;
			if (rollback)
				rollback.disabled = !this.rollbackTransaction ||
					(this.passwall.capabilities && this.passwall.capabilities.rollback === false);
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
			{ group: _('VPN overrides'), source: 'vpn_overrides', name: 'gemini', label: _('Gemini app and API'), domains: 'gemini.google.com, generativelanguage.googleapis.com', destination: _('Selected VPN') },
			{ group: _('VPN overrides'), source: 'vpn_overrides', name: 'android_check', label: _('Android internet checks'), domains: 'connectivitycheck.gstatic.com, connectivitycheck.android.com, clients3.google.com', destination: _('Selected VPN') },
			{ group: _('VPN overrides'), source: 'vpn_overrides', name: 'youtube_control', label: _('YouTube sign-in and controls'), domains: _('YouTube UI/API domains; video delivery is excluded'), destination: _('Selected VPN') },
			{ group: _('VPN overrides'), source: 'vpn_overrides', name: 'accounts_google', label: _('Google Account sign-in'), domains: 'accounts.google.com', destination: _('Selected VPN') },
			{ group: _('MITM-compatible services'), source: 'mitm_services', name: 'google_mitm', label: _('Google services'), domains: 'geosite:google', destination: _('Local SOCKS') },
			{ group: _('MITM-compatible services'), source: 'mitm_services', name: 'meta_mitm', label: _('Meta websites'), domains: 'geosite:meta', destination: _('Local SOCKS') },
			{ group: _('MITM-compatible services'), source: 'mitm_services', name: 'fastly_mitm', label: _('Fastly-backed websites'), domains: _('Fastly, Reddit, CNN, and BuzzFeed groups'), destination: _('Local SOCKS') },
			{ group: _('Regional direct access'), source: 'regional_direct', name: 'iran_direct', label: _('Iranian websites and IP addresses'), domains: 'geosite:ir, geoip:ir', destination: _('Direct connection') }
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
		var routingState = setup.routing || {};
		var shunts = optionList(passwall.shunt_nodes || passwall.shunts);
		var vpns = optionList(passwall.vpn_nodes || passwall.vpns);
		var selectedVpn = passwall.selected_vpn || (vpns[0] && vpns[0].id);
		var canReviewRouting = passwallState.compatible === true && passwall.writable === true &&
			routingState.recovery_pending !== true && shunts.length > 0 && vpns.length > 0;
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
					this.simpleRoutingTable(routingState, passwall),
					E('label', { for: 'xray-mitm-simple-vpn', style: 'display:block;font-weight:600;margin-bottom:.35rem' }, _('VPN for Gemini')),
					selectControl('xray-mitm-simple-vpn', vpns, selectedVpn, function() {
						dom.content(document.getElementById('xray-mitm-simple-routing-preview'), '');
					}),
					E('p', {}, E('button', {
						class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'reviewRecommendedRouting')
					}, _('Review selected routing'))),
					E('div', { id: 'xray-mitm-simple-routing-preview', 'aria-live': 'polite' })
				]) : ''
			]),
			E('div', { id: 'xray-mitm-simple-status', class: 'cbi-section cbi-tabcontainer',
				'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'status', style: pageStyle('status') }, [
				E('h3', {}, _('Status')),
				this.simpleStateRow(_('MITM'), status.running === true ? _('Running') : _('Stopped'), status.running === true ? 'good' : 'warn'),
				this.simpleStateRow(_('Routing'), routingState.recommended_matches_current === true ? _('Recommended') :
					(routingState.configured === true ? _('Custom') : _('Not configured')),
					routingState.configured === true ? 'good' : 'warn'),
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
					E('button', { class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'useRecommendedRouting') }, _('Use recommended setup')), ' ',
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
					{ id: 'xray-mitm-route-youtube-control', label: _('YouTube sign-in and controls'), description: _('YouTube UI/API domains; googlevideo.com is excluded so video delivery can use MITM.'), checked: routingState.youtube_control === true, onChange: selectionChanged },
					{ id: 'xray-mitm-route-accounts-google', label: _('Google Account sign-in'), description: 'accounts.google.com', checked: routingState.accounts_google === true, onChange: selectionChanged }
				], ruleSources.vpn_overrides),
				routingRuleCard('2', _('MITM-Compatible Services'), _('Destination: local SOCKS 127.0.0.1:10808'), _(
					'The assistant reuses or creates the localhost SOCKS node. Enable only service groups you have tested on your devices.'
				), [
					{ id: 'xray-mitm-route-google-mitm', label: _('Google services'), description: 'geosite:google', checked: routingState.google_mitm === true, onChange: selectionChanged },
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
					'Review builds a private temporary copy first. Nothing is changed until you apply that exact preview. A rollback copy is kept.'
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
