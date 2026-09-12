'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const modulePath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'xray-mitm', 'state.js');
const overviewPath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'view', 'xray-mitm', 'overview.js');
const menuPath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'root',
	'usr', 'share', 'luci', 'menu.d', 'luci-app-xray-mitm.json');

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
		'shunt-a', 'vpn-a', true, true, true, true, true, true,
		false, false, true, true, true, true
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
	const fakeLuCI = {
		bind: function(fn, context) { return fn.bind(context); },
		url: function(value) { return '/' + value; }
	};
	const overviewSource = fs.readFileSync(overviewPath, 'utf8');

	assert.doesNotMatch(overviewSource, /\brequire\s*\(/,
		'LuCI modules must use loader directives instead of CommonJS require()');
	assert.match(overviewSource, /var PROJECT_VERSION = '0\.4\.3';/,
		'LuCI dashboard keeps the current project version fallback');
	assert.match(overviewSource, /xray-mitm-version-badge/,
		'LuCI dashboard renders a visible application version badge');
	assert.doesNotMatch(overviewSource, /Recommended routing is already configured/,
		'Basic routing preview does not describe unchecked selections as recommended');
	assert.match(overviewSource, /Selected routing is already active/,
		'Basic routing preview reports the actual selected state');
	assert.match(overviewSource, /Apply selected routing/,
		'Basic routing preview applies the selected choices');
	assert.match(overviewSource, /Saved rule found \(inactive\)/,
		'Inactive existing rules are distinguishable from active assignments');
	assert.match(overviewSource, /Automatic setup prepares only the MITM service/,
		'Basic routing explains why automatic setup leaves assignments clear');
	assert.match(overviewSource, /useSimpleRecommendedRouting/,
		'Basic routing provides a recommended setup action');
	assert.match(overviewSource, /New to PassWall2\? Select the recommended choices/,
		'Basic routing explains the new-user setup flow');
	assert.match(overviewSource, /not all Google services/,
		'Google MITM option clearly states that it is a selective bundle');
	assert.match(overviewSource, /Google Meet web and signaling/,
		'Google Meet is exposed as a separate MITM-compatible routing group');
	assert.match(overviewSource, /audio\/video media may use UDP or separate media IPs/,
		'Google Meet explains the media transport limitation');

	const overview = loadLuciModule(overviewSource, modules, {
		E: fakeElement,
		_: function(value) { return value; },
		document: fakeDocument,
		L: fakeLuCI
	});

	assert.doesNotThrow(function() {
		overview.renderSetupGuide({ configured: false, running: false }, {}, {});
	});
	assert.strictEqual(typeof overview.switchDashboardPage, 'function');
}

function testSingleViewMenu() {
	const menu = JSON.parse(fs.readFileSync(menuPath, 'utf8'));
	const root = 'admin/services/xray-mitm';

	assert.deepStrictEqual(Object.keys(menu), [ root ]);
	assert.strictEqual(menu[root].action.type, 'view');
	assert.strictEqual(menu[root].action.path, 'xray-mitm/overview');
}

function testClientSideDashboardTabs() {
	function node(attributes) {
		return {
			attributes: attributes || {},
			style: {},
			className: '',
			getAttribute: function(name) { return this.attributes[name]; }
		};
	}

	const simple = node();
	const advanced = node();
	const panels = [
		node({ 'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'overview' }),
		node({ 'data-dashboard-panel-mode': 'basic', 'data-dashboard-panel-page': 'routing' }),
		node({ 'data-dashboard-panel-mode': 'advanced', 'data-dashboard-panel-page': 'overview' }),
		node({ 'data-dashboard-panel-mode': 'advanced', 'data-dashboard-panel-page': 'service' })
	];
	const rows = [
		node({ 'data-dashboard-tabs': 'mode' }),
		node({ 'data-dashboard-tabs': 'basic' }),
		node({ 'data-dashboard-tabs': 'advanced' })
	];
	const tabs = [
		node({ 'data-dashboard-tab-mode': 'mode', 'data-dashboard-tab-page': 'basic' }),
		node({ 'data-dashboard-tab-mode': 'mode', 'data-dashboard-tab-page': 'advanced' }),
		node({ 'data-dashboard-tab-mode': 'basic', 'data-dashboard-tab-page': 'overview' }),
		node({ 'data-dashboard-tab-mode': 'advanced', 'data-dashboard-tab-page': 'service' })
	];
	const fakeDocument = {
		createTextNode: function(value) { return value; },
		getElementById: function(id) {
			return id === 'xray-mitm-simple' ? simple :
				(id === 'xray-mitm-advanced' ? advanced : null);
		},
		querySelectorAll: function(selector) {
			return selector === '[data-dashboard-panel-mode]' ? panels :
				(selector === '[data-dashboard-tabs]' ? rows : tabs);
		}
	};
	const overviewSource = fs.readFileSync(overviewPath, 'utf8');
	assert.ok(overviewSource.includes("method: 'passWall2Activation'"),
		'overview polls background routing activation');
	assert.ok(overviewSource.includes('pollRoutingActivation'),
		'overview records routing activation completion');
	const overview = loadLuciModule(overviewSource, {
		view: { extend: function(methods) { return methods; } },
		rpc: { declare: function() { return function() {}; } },
		ui: { addNotification: function() {}, createHandlerFn: function() { return function() {}; } },
		dom: { content: function() {} },
		'xray-mitm.state': {}
	}, {
		E: function() {},
		_: function(value) { return value; },
		document: fakeDocument,
		L: { bind: function(fn, context) { return fn.bind(context); } }
	});

	overview.switchDashboardPage('mode', 'advanced');
	assert.strictEqual(simple.style.display, 'none');
	assert.strictEqual(advanced.style.display, '');
	assert.strictEqual(rows[1].style.display, 'none');
	assert.strictEqual(rows[2].style.display, '');
	assert.strictEqual(panels[2].style.display, '');
	assert.strictEqual(tabs[1].className, 'cbi-tab');

	overview.switchDashboardPage('advanced', 'service');
	assert.strictEqual(panels[2].style.display, 'none');
	assert.strictEqual(panels[3].style.display, '');
	assert.strictEqual(tabs[3].className, 'cbi-tab');
}

testPasswallSelection();
testSimpleState();
testRoutingArguments();
testRouteStatusAndProgress();
testOverviewLoadsAndRendersWithLuCIStateDependency();
testSingleViewMenu();
testClientSideDashboardTabs();
console.log('Frontend state tests passed.');
