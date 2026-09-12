#!/usr/bin/env ucode

'use strict';

import { mkdtemp, open, popen, rmdir, unlink } from 'fs';

const CTL = '/usr/sbin/xray-mitmctl';
const MAX_JSON = 128 * 1024;
const MAX_CERT = 32 * 1024;
const MAX_KEY = 64 * 1024;

function resultError(message) {
	return { ok: false, error: message };
}

function openCommand(argv) {
	// Older ucode accepts only a shell string. Quote every argument separately.
	let quoted = [];
	for (let arg in argv) {
		if (type(arg) != 'string' || index(arg, "\u0000") >= 0)
			return null;
		push(quoted, "'" + join("'\"'\"'", split(arg, "'")) + "'");
	}
	return popen(join(' ', quoted), 'r');
}

function runJson(argv) {
	let proc = openCommand(argv);

	if (!proc)
		return resultError('Unable to start the requested operation.');

	let output = proc.read(MAX_JSON + 1);
	let status = proc.close();

	if (output == null || length(output) > MAX_JSON)
		return resultError('The operation returned invalid output.');

	let parsed;

	try {
		parsed = json(output);
	}
	catch (e) {
		return resultError('The operation did not return valid JSON.');
	}

	if (type(parsed) != 'object')
		return resultError('The operation returned an invalid response.');

	if (status != 0 && parsed.ok != false)
		return resultError('The operation failed.');

	return parsed;
}

function validFingerprint(value) {
	return type(value) == 'string' && match(value, /^[A-Fa-f0-9]{64}$/);
}

function validSectionId(value) {
	return type(value) == 'string' && length(value) <= 128 &&
		match(value, /^[A-Za-z0-9_]+$/);
}

function validCommonName(value) {
	return type(value) == 'string' &&
		length(value) >= 1 && length(value) <= 64 &&
		match(value, /^[A-Za-z0-9][A-Za-z0-9 ._-]*$/);
}

function hasOneCertificate(pem) {
	return length(split(pem, '-----BEGIN CERTIFICATE-----')) == 2 &&
		length(split(pem, '-----END CERTIFICATE-----')) == 2;
}

function hasOnePrivateKey(pem) {
	if (index(pem, '-----BEGIN ENCRYPTED PRIVATE KEY-----') >= 0)
		return false;

	let begin = 0;
	let end = 0;
	let labels = [ 'PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY' ];

	for (let label in labels) {
		begin += length(split(pem, '-----BEGIN ' + label + '-----')) - 1;
		end += length(split(pem, '-----END ' + label + '-----')) - 1;
	}

	return begin == 1 && end == 1;
}

function writePrivate(path, value) {
	let file = open(path, 'wxe', 0o600);

	if (!file)
		return false;

	let written = file.write(value);
	file.close();
	return written == length(value);
}

function cleanupImport(dir) {
	if (!dir)
		return;

	unlink(dir + '/input.crt');
	unlink(dir + '/input.key');
	rmdir(dir);
}

function cleanupPlan(dir) {
	if (!dir)
		return;

	unlink(dir + '/request.json');
	rmdir(dir);
}

function validPlanRequest(args) {
	if (!validSectionId(args.shunt_node) || !validSectionId(args.vpn_node))
		return false;

	let flags = [
		'gemini', 'android_check', 'youtube_control', 'google_play', 'google_mitm', 'google_meet',
		'meta_mitm', 'fastly_mitm',
		'iran_direct', 'accounts_google', 'set_default_vpn',
		'set_localhost_proxy_zero'
	];

	for (let name in flags)
		if (type(args[name]) != 'bool')
			return false;

	return true;
}

const methods = {
	getStatus: {
		call: function() {
			return runJson([ CTL, 'status-json' ]);
		}
	},

	getSetupStatus: {
		call: function() {
			return runJson([ CTL, 'setup-status-json' ]);
		}
	},

	setupRecommended: {
		call: function() {
			return runJson([ CTL, 'setup-recommended' ]);
		}
	},

	runHealthCheck: {
		call: function() {
			return runJson([ CTL, 'health-json' ]);
		}
	},

	serviceAction: {
		args: { action: 'restart' },
		call: function(request) {
			let action = request.args.action;
			let allowed = [ 'start', 'restart', 'stop', 'enable', 'disable' ];

			if (index(allowed, action) < 0)
				return resultError('Unsupported service action.');

			return runJson([ CTL, 'service', action ]);
		}
	},

	installDefaultConfig: {
		call: function() {
			return runJson([ CTL, 'config-install-default' ]);
		}
	},

	getCertificateStatus: {
		call: function() {
			return runJson([ CTL, 'cert-status-json' ]);
		}
	},

	exportCertificate: {
		args: { slot: 'current' },
		call: function(request) {
			let slot = request.args.slot;

			if (index([ 'current', 'candidate', 'previous' ], slot) < 0)
				return resultError('Invalid certificate slot.');

			let proc = openCommand([ CTL, 'cert-export', slot ]);

			if (!proc)
				return resultError('Unable to export the public certificate.');

			let pem = proc.read(MAX_CERT + 1);
			let status = proc.close();

			if (status != 0 || pem == null || length(pem) > MAX_CERT ||
				!hasOneCertificate(pem) || index(pem, 'PRIVATE KEY') >= 0)
				return resultError('The selected public certificate is unavailable.');

			return { ok: true, slot, certificate_pem: pem };
		}
	},

	generateCandidate: {
		args: { common_name: 'MITM-DomainFronting', days: 3650 },
		call: function(request) {
			let commonName = request.args.common_name;
			let days = request.args.days;

			if (!validCommonName(commonName) || days < 365 || days > 3650)
				return resultError('Invalid certificate name or validity period.');

			return runJson([ CTL, 'cert-generate', commonName, '' + days ]);
		}
	},

	importCandidate: {
		args: { certificate_pem: '', private_key_pem: '' },
		call: function(request) {
			let cert = request.args.certificate_pem;
			let key = request.args.private_key_pem;

			if (type(cert) != 'string' || type(key) != 'string' ||
				length(cert) > MAX_CERT || length(key) > MAX_KEY ||
				index(cert, chr(0)) >= 0 || index(key, chr(0)) >= 0 ||
				!hasOneCertificate(cert) || !hasOnePrivateKey(key))
				return resultError('The certificate or private key has an invalid format.');

			let dir = mkdtemp('/tmp/xray-mitm-rpc.XXXXXX');

			if (!dir)
				return resultError('Unable to create private temporary storage.');

			if (!writePrivate(dir + '/input.crt', cert) ||
				!writePrivate(dir + '/input.key', key)) {
				cleanupImport(dir);
				return resultError('Unable to prepare the private import.');
			}

			let result = runJson([ CTL, 'cert-prepare-import', dir ]);
			cleanupImport(dir);
			return result;
		}
	},

	activateCandidate: {
		args: { expected_fingerprint: '' },
		call: function(request) {
			let fingerprint = request.args.expected_fingerprint;

			if (!validFingerprint(fingerprint))
				return resultError('Invalid certificate fingerprint.');

			return runJson([ CTL, 'cert-activate', fingerprint ]);
		}
	},

	discardCandidate: {
		args: { expected_fingerprint: '' },
		call: function(request) {
			let fingerprint = request.args.expected_fingerprint;

			if (!validFingerprint(fingerprint))
				return resultError('Invalid certificate fingerprint.');

			return runJson([ CTL, 'cert-discard', fingerprint ]);
		}
	},

	rollbackCertificate: {
		args: { expected_current_fingerprint: '' },
		call: function(request) {
			let fingerprint = request.args.expected_current_fingerprint;

			if (!validFingerprint(fingerprint))
				return resultError('Invalid certificate fingerprint.');

			return runJson([ CTL, 'cert-rollback', fingerprint ]);
		}
	},

	adoptLegacyCertificate: {
		call: function() {
			return runJson([ CTL, 'cert-adopt-legacy' ]);
		}
	},

	inspectPassWall2: {
		call: function() {
			return runJson([ CTL, 'passwall2', 'inspect' ]);
		}
	},

	recoverPassWall2: {
		call: function() {
			return runJson([ CTL, 'passwall2', 'recover' ]);
		}
	},

	planPassWall2: {
		args: {
			shunt_node: '',
			vpn_node: '',
			gemini: true,
			android_check: true,
			youtube_control: true,
			google_play: true,
			google_mitm: true,
			google_meet: false,
			meta_mitm: false,
			fastly_mitm: false,
			iran_direct: true,
			accounts_google: true,
			set_default_vpn: true,
			set_localhost_proxy_zero: true
		},
		call: function(request) {
			if (!validPlanRequest(request.args))
				return resultError('The routing request is invalid.');

			let dir = mkdtemp('/tmp/xray-mitm-plan.XXXXXX');

			if (!dir)
				return resultError('Unable to create private temporary storage.');

			let payload = sprintf('%J\n', request.args);

			if (!writePrivate(dir + '/request.json', payload)) {
				cleanupPlan(dir);
				return resultError('Unable to prepare the routing preview.');
			}

			let result = runJson([ CTL, 'passwall2', 'plan', dir + '/request.json' ]);
			cleanupPlan(dir);
			return result;
		}
	},

	applyPassWall2: {
		args: { token: '' },
		call: function(request) {
			if (type(request.args.token) != 'string' ||
				!match(request.args.token, /^[a-f0-9]{64}$/))
				return resultError('Invalid or expired routing preview token.');

			return runJson([ CTL, 'passwall2', 'apply', request.args.token ]);
		}
	},

	passWall2Activation: {
		args: { transaction: '' },
		call: function(request) {
			if (type(request.args.transaction) != 'string' ||
				!match(request.args.transaction, /^[a-f0-9]{64}$/))
				return resultError('Invalid routing activation transaction.');

			return runJson([ CTL, 'passwall2', 'activation-status', request.args.transaction ]);
		}
	},

	rollbackPassWall2: {
		args: { transaction: '' },
		call: function(request) {
			if (type(request.args.transaction) != 'string' ||
				!match(request.args.transaction, /^[a-f0-9]{64}$/))
				return resultError('Invalid rollback transaction.');

			return runJson([ CTL, 'passwall2', 'rollback', request.args.transaction ]);
		}
	}
};

return { 'luci.xray-mitm': methods };
