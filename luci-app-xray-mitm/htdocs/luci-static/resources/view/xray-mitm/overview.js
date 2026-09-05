'use strict';
'require view';
'require rpc';
'require ui';
'require dom';

var callGetStatus = rpc.declare({
	object: 'luci.xray-mitm',
	method: 'getStatus',
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
	'shunt_node', 'vpn_node', 'lan_zone', 'gemini', 'android_check',
	'youtube_control', 'google_mitm', 'iran_direct', 'accounts_google',
	'set_default_vpn', 'set_global_shunt', 'set_localhost_proxy_zero',
	'block_quic'
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

function optionList(items) {
	if (!Array.isArray(items))
		return [];

	return items.map(function(item) {
		if (typeof item === 'string')
			return { id: item, label: item };

		return {
			id: item.id || item.name || item.section,
			label: item.label || item.remarks || item.name || item.id || item.section
		};
	}).filter(function(item) { return !!item.id; });
}

function selectControl(id, items, selected) {
	var select = E('select', { id: id, class: 'cbi-input-select' });

	items.forEach(function(item) {
		select.appendChild(E('option', {
			value: item.id,
			selected: item.id === selected ? '' : null
		}, textNode(item.label)));
	});

	return select;
}

function checkControl(id, label, checked) {
	return E('label', { style: 'display:block; margin:.45em 0' }, [
		E('input', { id: id, type: 'checkbox', checked: checked ? '' : null }),
		' ', label
	]);
}

function operationList(plan) {
	var operations = plan.operations || plan.changes || [];

	if (!Array.isArray(operations) || !operations.length)
		return E('p', {}, _('No configuration changes are required.'));

	return E('ul', {}, operations.map(function(operation) {
		if (typeof operation === 'string')
			return E('li', {}, textNode(operation));

			return E('li', {}, textNode(operation.description || operation.action || operation.name));
	}));
}

return view.extend({
	load: function() {
		return Promise.all([
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
		output.textContent = _('Running health check…');

		callHealth().then(function(result) {
			if (!result || result.ok === false) {
				var error = new Error(result && result.error ? result.error : _('Health check failed.'));
				error.details = result && (result.output || result.details || result.message);
				throw error;
			}

			var lines = result.lines || result.details || result.output || result.message;
			output.textContent = Array.isArray(lines) ? lines.join('\n') : text(lines, _('Health check passed.'));
			notification(_('MITM health check passed.'), 'info');
		}).catch(function(error) {
			output.textContent = text(error.details || error.message, _('Health check failed.'));
			notification(_('MITM health check failed.'), 'error');
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
		var values = routingParams.map(function(name) {
			var element = document.getElementById('xray-mitm-route-' + name.replace(/_/g, '-'));

			if (!element)
				return name === 'lan_zone' ? '' : false;

			return element.type === 'checkbox' ? element.checked : element.value;
		});
		var button = ev.currentTarget;
		var output = document.getElementById('xray-mitm-routing-preview');
		setBusy(button, true);

		callPlanPassWall2.apply(null, values).then(assertOk).then(L.bind(function(plan) {
			this.planToken = plan.token || null;
			this.lastPlan = plan;
			dom.content(output, [
				E('h4', {}, _('Preview')),
				operationList(plan),
					plan.warning ? E('div', { class: 'alert-message warning' }, textNode(plan.warning)) : ''
				]);

			var apply = document.getElementById('xray-mitm-routing-apply');
			apply.disabled = !this.planToken || plan.writable === false ||
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
			_('PassWall2 routing changes applied.'), false).then(L.bind(function(result) {
			if (!result || !result.ok)
				return;

			this.rollbackTransaction = result.transaction || null;
			this.planToken = null;
			document.getElementById('xray-mitm-routing-apply').disabled = true;
			document.getElementById('xray-mitm-routing-rollback').disabled =
				!this.rollbackTransaction ||
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

	renderService: function(status) {
		var running = status.running === true ? _('Running') :
			(status.running === false ? _('Stopped') : _('Unknown'));
		var enabled = status.enabled === true ? _('Enabled') :
			(status.enabled === false ? _('Disabled') : _('Unknown'));
		var configured = status.configured === true ? _('Ready') :
			(status.configured === false ? _('Not provisioned') : _('Unknown'));

		return E('div', { class: 'cbi-section' }, [
			E('h3', {}, _('Service')),
			E('table', { class: 'table' }, [
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left', width: '35%' }, _('State')), E('td', { class: 'td left' }, running) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Start at boot')), E('td', { class: 'td left' }, enabled) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Configuration')), E('td', { class: 'td left' }, configured) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Local SOCKS listener')), E('td', { class: 'td left' }, '127.0.0.1:10808') ])
			]),
			E('p', {}, [
				E('button', { class: 'btn cbi-button-positive', click: ui.createHandlerFn(this, 'serviceAction', 'start') }, _('Start')), ' ',
				E('button', { class: 'btn cbi-button-action', click: ui.createHandlerFn(this, 'serviceAction', 'restart') }, _('Restart')), ' ',
				E('button', { class: 'btn cbi-button-negative', click: ui.createHandlerFn(this, 'serviceAction', 'stop') }, _('Stop')), ' ',
				E('button', { class: 'btn cbi-button-positive', click: ui.createHandlerFn(this, 'serviceAction', 'enable') }, _('Enable at boot')), ' ',
				E('button', { class: 'btn cbi-button-negative', click: ui.createHandlerFn(this, 'serviceAction', 'disable') }, _('Disable at boot'))
			]),
			status.configured === false ? E('p', {}, E('button', {
				class: 'btn cbi-button-action',
				click: ui.createHandlerFn(this, 'installConfig')
			}, _('Install packaged default configuration'))) : '',
			E('p', {}, E('button', {
				class: 'btn cbi-button-action',
				click: ui.createHandlerFn(this, 'runHealth')
			}, _('Run health check'))),
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
			E('h3', {}, _('Certificate authority')),
			E('p', {}, _(
				'Only public CA certificates can be downloaded. The private key remains on the router and is stored with mode 0600.'
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
		var capabilities = inspect.capabilities || {};
		var recoveryPending = inspect.recovery_pending === true;
		var compatible = inspect.available !== false && inspect.compatible === true && shunts.length && vpns.length;
		var canPlan = !recoveryPending && compatible && inspect.writable === true && capabilities.plan !== false;
		var canRollback = !recoveryPending && capabilities.rollback !== false && !!this.rollbackTransaction;
		var selectedShunt = inspect.selected_shunt || inspect.current_shunt || (shunts[0] && shunts[0].id);
		var selectedVpn = inspect.selected_vpn || (vpns[0] && vpns[0].id);

		return E('div', { class: 'cbi-section' }, [
			E('h3', {}, _('PassWall2 routing (optional)')),
			E('p', {}, _(
				'Installation never changes PassWall2, DNS, routing, or firewall settings. This wizard previews a redacted transaction before it can be applied.'
			)),
			E('table', { class: 'table' }, [
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left', width: '35%' }, _('PassWall2 found')), E('td', { class: 'td left' }, yesNo(inspect.available)) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Schema compatible')), E('td', { class: 'td left' }, yesNo(inspect.compatible)) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Pending user changes')), E('td', { class: 'td left' }, yesNo(inspect.pending_changes)) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Interrupted transaction')), E('td', { class: 'td left' }, recoveryPending ? _('Recovery required') : _('None')) ]),
				E('tr', { class: 'tr' }, [ E('td', { class: 'td left' }, _('Detected package manager')), E('td', { class: 'td left' }, textNode(inspect.package_manager)) ])
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
				textNode(inspect.message || inspect.error, _('No compatible existing shunt and VPN node combination was found. Routing remains read-only.'))) : '',
			compatible && !canPlan ? E('div', { class: 'alert-message warning' }, _(
				'Save or revert pending PassWall2 changes before creating a routing preview.'
			)) : '',
			compatible ? E('div', {}, [
				E('div', { class: 'cbi-value' }, [
					E('label', { class: 'cbi-value-title' }, _('Existing shunt node')),
					E('div', { class: 'cbi-value-field' }, selectControl('xray-mitm-route-shunt-node', shunts, selectedShunt))
				]),
				E('div', { class: 'cbi-value' }, [
					E('label', { class: 'cbi-value-title' }, _('Existing VPN node')),
					E('div', { class: 'cbi-value-field' }, selectControl('xray-mitm-route-vpn-node', vpns, selectedVpn))
				]),
				E('h4', {}, _('Managed rules')),
				checkControl('xray-mitm-route-gemini', _('Gemini control/API through selected VPN'), true),
				checkControl('xray-mitm-route-android-check', _('Android connectivity checks through selected VPN'), false),
				checkControl('xray-mitm-route-youtube-control', _('YouTube control/account API through selected VPN (never video delivery)'), false),
				checkControl('xray-mitm-route-google-mitm', _('Google through MITM Domain Fronting'), true),
				checkControl('xray-mitm-route-iran-direct', _('Iranian domains and IPs direct'), true),
				checkControl('xray-mitm-route-accounts-google', _('Also put accounts.google.com in the Gemini VPN rule'), false),
				E('h4', {}, _('Separate routing changes')),
				checkControl('xray-mitm-route-set-default-vpn', _('Make selected VPN the shunt default'), false),
				checkControl('xray-mitm-route-set-localhost-proxy-zero', _('Set localhost_proxy=0 to prevent recapture'), true),
				E('div', { class: 'alert-message warning' }, _(
					'accounts.google.com changes authentication routing beyond Gemini. Enable it only when that broader behavior is intended. Firewall, QUIC, and DNS settings remain outside this transaction.'
				)),
				E('p', {}, [
					E('button', { class: 'btn cbi-button-action', disabled: canPlan ? null : '', click: ui.createHandlerFn(this, 'planRouting') }, _('Preview changes')), ' ',
					E('button', { id: 'xray-mitm-routing-apply', class: 'btn cbi-button-positive', disabled: '', click: ui.createHandlerFn(this, 'applyRouting') }, _('Apply preview')), ' ',
					E('button', { id: 'xray-mitm-routing-rollback', class: 'btn cbi-button-negative', disabled: canRollback ? null : '', click: ui.createHandlerFn(this, 'rollbackRouting') }, _('Rollback last transaction'))
				]),
				E('div', { id: 'xray-mitm-routing-preview' })
			]) : ''
		]);
	},

	render: function(data) {
		this.status = data[0] || {};
		this.certificates = data[1] || {};
		this.passwall = data[2] || {};
		this.planToken = null;
		this.rollbackTransaction = this.passwall.rollback_transaction || null;

		return E('div', {}, [
			E('h2', {}, _('MITM Domain Fronting')),
			E('p', {}, _(
				'Architecture-independent management for a standalone Xray process with localhost-only listeners.'
			)),
				this.status.ok === false ? E('div', { class: 'alert-message danger' }, textNode(this.status.error, _('Unable to read service status.'))) : '',
			this.renderService(this.status),
			this.renderCertificates(this.certificates),
			this.renderRouting(this.passwall),
			E('div', { class: 'alert-message warning' }, _(
				'Trust the public CA only on devices you control. Never copy, publish, or download the router private CA key.'
			))
		]);
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
