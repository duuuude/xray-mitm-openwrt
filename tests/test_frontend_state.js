'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const modulePath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'xray-mitm', 'state.js');
const overviewPath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'view', 'xray-mitm', 'overview.js');

function loadLuciModule(moduleSource, modules, globals) {
	const dependencies = [];
	const directivePattern = /^\s*'require\s+([^\s']+)(?:\s+as\s+([A-Za-z_$][\w$]*))?';\s*$/gm;
	let match;

	while ((match = directivePattern.exec(moduleSource)) !== null) {
		const moduleName = match[1];
		const binding = match[2] || moduleName.split('.').pop();

		assert.ok(Object.prototype.hasOwnProperty.call(modules, moduleName),
			'LuCI dependency is available: ' + moduleName);
		dependencies.push({ binding: binding, value: modules[moduleName] });
	}

	const globalNames = Object.keys(globals || {});
	const parameterNames = dependencies.map(item => item.binding).concat(globalNames);
	const parameterValues = dependencies.map(item => item.value)
		.concat(globalNames.map(name => globals[name]));

	return Function.apply(null, parameterNames.concat(moduleSource))
		.apply(null, parameterValues);
}

const baseclass = {
	extend: function(methods) {
		function State() {}
		State.prototype = methods;
		return State;
	}
};
const State = Function('baseclass', fs.readFileSync(modulePath, 'utf8'))(baseclass);
const state = new State();

function testPasswallSelection() {
	const selection = state.passwallSelection({
		shunts: [ { section: 'shunt-a' } ],
		vpns: [ { name: 'vpn-a' }, 'vpn-b' ],
		selected_vpn: 'vpn-b',
		compatible: true
	});

	assert.deepStrictEqual(selection.shunts.map(item => item.id), [ 'shunt-a' ]);
	assert.deepStrictEqual(selection.vpns.map(item => item.id), [ 'vpn-a', 'vpn-b' ]);
	assert.strictEqual(selection.selectedShunt, 'shunt-a');
	assert.strictEqual(selection.selectedVpn, 'vpn-b');
	assert.strictEqual(selection.compatible, true);
}

function testSimpleState() {
	const result = state.deriveSimpleState({
		ready: true,
		service: { boot_enabled: true },
		certificate: {
			ready: false,
			candidate_requires_attention: true
		},
		passwall2: {
			installed: true,
			shunt_available: true,
			vpn_available: true,
			compatible: true
		},
		routing: { recovery_pending: false }
	}, { running: false }, {}, {
		shunt_nodes: [ 'shunt-a' ],
		vpn_nodes: [ 'vpn-a' ],
		writable: true,
		compatible: true
	});

	assert.strictEqual(result.setupComplete, true);
	assert.strictEqual(result.setupBlocked, true);
	assert.strictEqual(result.mitmRunning, false);
	assert.strictEqual(result.canReviewRouting, true);
	assert.strictEqual(result.selectedVpn, 'vpn-a');
}

function testRoutingArguments() {
	const values = state.recommendedChoices();
	values.shunt_node = 'shunt-a';
	values.vpn_node = 'vpn-a';

	assert.deepStrictEqual(state.routingArguments(values), [
		'shunt-a', 'vpn-a', true, false, false, true,
		false, false, true, false, false, true
	]);

	assert.strictEqual(state.routingChoices({ google_mitm: 1 }).google_mitm, false);
	assert.strictEqual(state.routingChoices({ google_mitm: true }).google_mitm, true);
}

function testRouteStatusAndProgress() {
	assert.deepStrictEqual(state.routeStatus('existing', false), { kind: 'existing', tone: 'info' });
	assert.deepStrictEqual(state.routeStatus('managed', false), { kind: 'managed', tone: 'muted' });
	assert.deepStrictEqual(state.routeStatus(undefined, true), { kind: 'active', tone: 'good' });

	const progress = state.setupProgress({ configured: true, running: true }, {
		slots: { current: { present: true } }
	}, { routing_state: { iran_direct: true } });

	assert.deepStrictEqual(progress, {
		firstTime: false,
		serviceReady: true,
		certificateReady: true,
		mitmRunning: true,
		routingReady: true
	});
}

function testOverviewLoadsAndRendersWithLuCIStateDependency() {
	const fakeView = {
		extend: function(methods) { return methods; }
	};
	const fakeRpc = {
		declare: function() { return function() {}; }
	};
	const fakeUi = {
		addNotification: function() {},
		createHandlerFn: function() { return function() {}; }
	};
	const fakeDom = { content: function() {} };
	const fakeState = {
		setupProgress: function() {
			return { firstTime: true, routingReady: false };
		}
	};
	const modules = {
		view: fakeView,
		rpc: fakeRpc,
		ui: fakeUi,
		dom: fakeDom,
		'xray-mitm.state': fakeState
	};
	const fakeElement = function(tag, attributes, children) {
		return { tag: tag, attributes: attributes, children: children };
	};
	const fakeDocument = { createTextNode: function(value) { return value; } };
	const fakeLuCI = { bind: function(fn, context) { return fn.bind(context); } };
	const overviewSource = fs.readFileSync(overviewPath, 'utf8');

	assert.doesNotMatch(overviewSource, /\brequire\s*\(/,
		'LuCI modules must use loader directives instead of CommonJS require()');

	const overview = loadLuciModule(overviewSource, modules, {
		E: fakeElement,
		_: function(value) { return value; },
		document: fakeDocument,
		L: fakeLuCI
	});

	assert.doesNotThrow(function() {
		overview.renderSetupGuide({ configured: false, running: false }, {}, {});
	});
}

testPasswallSelection();
testSimpleState();
testRoutingArguments();
testRouteStatusAndProgress();
testOverviewLoadsAndRendersWithLuCIStateDependency();
console.log('Frontend state tests passed.');
