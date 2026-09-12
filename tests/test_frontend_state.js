'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const modulePath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'xray-mitm', 'state.js');
const uiModulePath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'xray-mitm', 'ui.js');
const overviewPath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'view', 'xray-mitm', 'overview.js');
const packageMakefilePath = path.join(__dirname, '..', 'xray-mitm', 'Makefile');
const rpcPath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'root',
	'usr', 'share', 'rpcd', 'ucode', 'xray-mitm.uc');
const ctlPath = path.join(__dirname, '..', 'xray-mitm', 'files', 'usr', 'sbin',
	'xray-mitmctl');
const recommendedPath = path.join(__dirname, 'fixtures', 'recommended-routing.json');
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

function loadUiModule(fakeState, fakeUi, globals) {
	return loadLuciModule(fs.readFileSync(uiModulePath, 'utf8'), {
		ui: fakeUi,
		'xray-mitm.state': fakeState
	}, globals);
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
	const expectedFields = [
		'gemini', 'android_check', 'youtube_control', 'google_play',
		'google_mitm', 'google_meet', 'meta_mitm', 'fastly_mitm',
		'iran_direct', 'accounts_google', 'set_default_vpn',
		'set_localhost_proxy_zero'
	];
	const recommended = JSON.parse(fs.readFileSync(recommendedPath, 'utf8'));
	const values = state.recommendedChoices();

	assert.deepStrictEqual(state.routingFieldNames(), expectedFields);
	assert.deepStrictEqual(values, recommended);
	values.shunt_node = 'shunt-a';
	values.vpn_node = 'vpn-a';
	assert.deepStrictEqual(state.routingArguments(values), [
		'shunt-a', 'vpn-a', ...expectedFields.map(function(name) { return recommended[name]; })
	]);

	assert.deepStrictEqual(state.normalizeRoutingChoices({ google_meet: true }, {
		google_play: true
	}), Object.assign({}, state.routingChoices({ google_meet: true }), { google_play: true }));
	assert.strictEqual(state.routingChoices({ google_mitm: 1 }).google_mitm, false);
	assert.strictEqual(state.routingChoices({ google_mitm: true }).google_mitm, true);
}

function testRoutingContractParity() {
	const fields = state.routingFieldNames();
	const rpcSource = fs.readFileSync(rpcPath, 'utf8');
	const ctlSource = fs.readFileSync(ctlPath, 'utf8');
	const recommended = JSON.parse(fs.readFileSync(recommendedPath, 'utf8'));
	const flagsMatch = rpcSource.match(/let flags = \[([\s\S]*?)\];/);
	const defaultsMatch = rpcSource.match(/planPassWall2:\s*{\s*args:\s*{([\s\S]*?)\n\s*},\s*call:/);

	assert.ok(flagsMatch, 'rpcd exposes the routing flag contract');
	const rpcFields = Array.from(flagsMatch[1].matchAll(/'([^']+)'/g)).map(function(match) {
		return match[1];
	});
	assert.deepStrictEqual(rpcFields, fields,
		'frontend routing fields match the rpcd plan contract');
	assert.ok(defaultsMatch, 'rpcd exposes routing defaults');
	const rpcDefaults = {};
	fields.forEach(function(name) {
		const match = defaultsMatch[1].match(new RegExp('\\b' + name + ':\\s*(true|false)'));
		assert.ok(match, 'rpcd defines a default for routing field ' + name);
		rpcDefaults[name] = match[1] === 'true';
	});
	assert.deepStrictEqual(rpcDefaults, recommended,
		'rpcd defaults match the product recommended preset');
	assert.match(fs.readFileSync(overviewPath, 'utf8'),
		/\[ 'shunt_node', 'vpn_node' \]\.concat\(state\.routingFieldNames\(\)\)/,
		'overview builds routing arguments from the shared field contract');
	assert.match(fs.readFileSync(overviewPath, 'utf8'),
		/this\.simpleHiddenRouting = state\.recommendedChoices\(\)/,
		'Basic routing uses the canonical recommended preset');
	fields.forEach(function(name) {
		assert.match(ctlSource, new RegExp('routing_state\\.' + name),
			'control status evaluates routing field ' + name);
	});
}

function testRouteStatusAndProgress() {
	assert.deepStrictEqual(state.routeStatus('existing', false), { kind: 'existing', tone: 'info' });
	assert.deepStrictEqual(state.routeStatus('managed', false), { kind: 'managed', tone: 'muted' });
	assert.deepStrictEqual(state.routeStatus(undefined, true), { kind: 'active', tone: 'good' });
	assert.deepStrictEqual(state.deriveBasicRoutingStatus({ configured: true, recommended_matches_current: true }),
		{ kind: 'recommended', tone: 'good' });
	assert.deepStrictEqual(state.deriveBasicRoutingStatus({ configured: true, recommended_matches_current: false }),
		{ kind: 'custom', tone: 'good' });
	assert.deepStrictEqual(state.deriveBasicRoutingStatus({ configured: false, recommended_matches_current: true }),
		{ kind: 'not_configured', tone: 'warn' });
	assert.deepStrictEqual(state.deriveBasicRoutingStatus({}, state.recommendedChoices()),
		{ kind: 'recommended', tone: 'good' });
	assert.deepStrictEqual(state.deriveBasicRoutingStatus({}, Object.assign({}, state.recommendedChoices(), { google_meet: false })),
		{ kind: 'custom', tone: 'good' });

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

function testExtractedUiHelpers() {
	const fakeElement = function(tag, attributes, children) {
		return { tag: tag, attributes: attributes || {}, children: children };
	};
	const helpers = loadUiModule(state, {
		addNotification: function() {}
	}, {
		E: fakeElement,
		_: function(value) { return value; },
		document: { createTextNode: function(value) { return value; } }
	});

	assert.strictEqual(helpers.text('', 'fallback'), 'fallback');
	assert.strictEqual(helpers.text(42), '42');
	assert.deepStrictEqual(helpers.optionList([
		'vpn-a',
		{ id: 'vpn-b', remarks: 'VPN B', group: 'paid', protocol: 'trojan' },
		{ name: 'vpn-c', label: 'VPN C' },
		{}
	]), [
		{ id: 'vpn-a', label: 'vpn-a' },
		{ id: 'vpn-b', group: 'paid', label: 'VPN B — paid · trojan' },
		{ id: 'vpn-c', group: '', label: 'VPN C' }
	]);
	assert.deepStrictEqual(helpers.routeStatus('existing', false), {
		label: 'Saved rule found (inactive)', tone: 'info'
	});
	assert.deepStrictEqual(helpers.routeStatus(undefined, true), {
		label: 'Active now', tone: 'good'
	});
	assert.strictEqual(helpers.slotPresent({ fingerprint: 'abc' }), true);
	assert.deepStrictEqual(helpers.slotData({ slots: { current: { present: true } } }, 'current'), {
		present: true
	});
	assert.strictEqual(helpers.assertOk({ ok: true }).ok, true);
	assert.throws(function() { helpers.assertOk({ ok: false, message: 'failed' }); }, /failed/);
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
		routingFieldNames: function() { return []; },
		routeStatus: function(source, active) { return state.routeStatus(source, active); },
		setupProgress: function() {
			return { firstTime: true, routingReady: false };
		}
	};
	const fakeElement = function(tag, attributes, children) {
		return { tag: tag, attributes: attributes, children: children };
	};
	const fakeDocument = { createTextNode: function(value) { return value; } };
	const fakeLuCI = {
		bind: function(fn, context) { return fn.bind(context); },
		url: function(value) { return '/' + value; }
	};
	const modules = {
		view: fakeView,
		rpc: fakeRpc,
		ui: fakeUi,
		dom: fakeDom,
		'xray-mitm.state': fakeState,
		'xray-mitm.ui': loadUiModule(fakeState, fakeUi, {
			E: fakeElement,
			_: function(value) { return value; },
			document: fakeDocument
		})
	};
	const overviewSource = fs.readFileSync(overviewPath, 'utf8');
	const frontendSource = overviewSource + '\n' + fs.readFileSync(uiModulePath, 'utf8');
	const packageSource = fs.readFileSync(packageMakefilePath, 'utf8');
	const packageVersionMatch = packageSource.match(/^PKG_VERSION:=([^\r\n]+)$/m);

	assert.doesNotMatch(overviewSource, /\brequire\s*\(/,
		'LuCI modules must use loader directives instead of CommonJS require()');
	assert.ok(packageVersionMatch, 'package Makefile declares PKG_VERSION');
	assert.ok(overviewSource.includes("var PROJECT_VERSION = '" + packageVersionMatch[1] + "';"),
		'LuCI dashboard fallback matches the package version');
	assert.match(frontendSource, /xray-mitm-version-badge/,
		'LuCI dashboard renders a visible application version badge');
	assert.doesNotMatch(overviewSource, /Recommended routing is already configured/,
		'Basic routing preview does not describe unchecked selections as recommended');
	assert.match(overviewSource, /Selected routing is already active/,
		'Basic routing preview reports the actual selected state');
	assert.match(frontendSource, /Apply selected routing/,
		'Basic routing preview applies the selected choices');
	assert.match(frontendSource, /Saved rule found \(inactive\)/,
		'Inactive existing rules are distinguishable from active assignments');
	assert.match(frontendSource, /Automatic setup prepares only the MITM service/,
		'Basic routing explains why automatic setup leaves assignments clear');
	assert.match(frontendSource, /useSimpleRecommendedRouting/,
		'Basic routing provides a recommended setup action');
	assert.match(frontendSource, /New to PassWall2\? Select the recommended choices/,
		'Basic routing explains the new-user setup flow');
	assert.match(frontendSource, /Recommended routing/,
		'Basic routing shows the recommended destination summary');
	assert.match(frontendSource, /Gemini and Google app\/control traffic/,
		'Basic routing summary identifies VPN-routed Google app traffic');
	assert.match(frontendSource, /Google Drive and YouTube video.*Local SOCKS \(MITM\)/s,
		'Basic routing summary identifies the selective Google MITM route');
	assert.match(frontendSource, /Customize routing/,
		'Basic routing keeps detailed choices available under a customization section');
	assert.match(frontendSource, /Meet audio and video media may use UDP or separate media IPs/,
		'Basic routing summary carries the Google Meet media limitation');
	assert.match(frontendSource, /not all Google services/,
		'Google MITM option clearly states that it is a selective bundle');
	assert.match(frontendSource, /Google Meet web and signaling/,
		'Google Meet is exposed as a separate MITM-compatible routing group');
	assert.match(frontendSource, /audio\/video media may use UDP or separate media IPs/,
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
	assert.ok(overviewSource.includes("id: 'xray-mitm-routing-busy'"),
		'overview locks the page during routing activation');
	assert.ok(overviewSource.includes('Elapsed time: 0 seconds'),
		'overview shows elapsed routing activation time');
	assert.ok(overviewSource.includes('All routing controls are locked until the router confirms completion.'),
		'overview tells users to wait for routing confirmation');
	assert.ok(overviewSource.includes('Applying this routing may briefly interrupt traffic.'),
		'basic routing explains the apply interruption');
	assert.ok(overviewSource.includes('keep this page open while PassWall2 restarts and confirms the changes.'),
		'advanced routing explains the apply wait');
	assert.ok(overviewSource.includes('ROUTING_POLL_ATTEMPTS'),
		'overview bounds routing activation polling');
	const overview = loadLuciModule(overviewSource, {
		view: { extend: function(methods) { return methods; } },
		rpc: { declare: function() { return function() {}; } },
		ui: { addNotification: function() {}, createHandlerFn: function() { return function() {}; } },
		dom: { content: function() {} },
		'xray-mitm.state': {
			routingFieldNames: function() { return []; },
			routeStatus: function(source, active) { return state.routeStatus(source, active); }
		},
		'xray-mitm.ui': loadUiModule({
			routeStatus: function(source, active) { return state.routeStatus(source, active); }
		}, { addNotification: function() {} }, {
			E: function() {},
			_: function(value) { return value; },
			document: fakeDocument
		})
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

function testRoutingBusyOverlayLifecycle() {
	const root = { children: [], attributes: {}, appendChild: function(child) {
			child.parentNode = this;
			this.children.push(child);
		}, removeChild: function(child) {
			this.children = this.children.filter(function(item) { return item !== child; });
			child.parentNode = null;
		} };
	const documentElement = {
		attributes: {},
		setAttribute: function(name, value) { this.attributes[name] = value; },
		removeAttribute: function(name) { delete this.attributes[name]; }
	};

	function makeElement(tag, attributes, children) {
		const element = {
			tag: tag,
			attributes: attributes || {},
			children: [],
			parentNode: null,
			textContent: typeof children === 'string' ? children : '',
			appendChild: function(child) {
				child.parentNode = this;
				this.children.push(child);
			},
			focus: function() { this.focused = true; }
		};

		if (Array.isArray(children))
			children.forEach(function(child) { if (child && typeof child === 'object') element.appendChild(child); });

		return element;
	}

	function findById(element, id) {
		if (!element)
			return null;
		if (element.attributes && element.attributes.id === id)
			return element;
		for (const child of element.children || []) {
			const found = findById(child, id);
			if (found)
				return found;
		}
		return null;
	}

	const fakeDocument = {
		body: root,
		documentElement: documentElement,
		getElementById: function(id) { return findById(root, id); }
	};
	const fakeWindow = {
		setInterval: function() { return 17; },
		clearInterval: function(id) { fakeWindow.cleared = id; }
	};
	const overviewSource = fs.readFileSync(overviewPath, 'utf8');
	const overview = loadLuciModule(overviewSource, {
		view: { extend: function(methods) { return methods; } },
		rpc: { declare: function() { return function() {}; } },
		ui: { addNotification: function() {}, createHandlerFn: function() { return function() {}; } },
		dom: { content: function() {} },
		'xray-mitm.state': {
			routingFieldNames: function() { return []; },
			routeStatus: function(source, active) { return state.routeStatus(source, active); }
		},
		'xray-mitm.ui': loadUiModule({
			routeStatus: function(source, active) { return state.routeStatus(source, active); }
		}, { addNotification: function() {} }, {
			E: makeElement,
			_: function(value) { return value; },
			document: fakeDocument
		})
	}, {
		E: makeElement,
		_: function(value) { return value; },
		document: fakeDocument,
		window: fakeWindow,
		L: { bind: function(fn, context) { return fn.bind(context); } }
	});

	overview.routingBusy = false;
	overview.routingBusyTimer = null;
	overview.setRoutingBusy(true);
	assert.strictEqual(overview.routingBusy, true);
	assert.strictEqual(root.children.length, 1);
	assert.strictEqual(fakeDocument.getElementById('xray-mitm-routing-busy-title').textContent,
		'Applying routing changes…');
	assert.strictEqual(documentElement.attributes['aria-busy'], 'true');
	overview.setRoutingBusyMessage('Waiting for PassWall2…', 'Still applying');
	assert.strictEqual(fakeDocument.getElementById('xray-mitm-routing-busy-detail').textContent,
		'Still applying');
	overview.setRoutingBusy(false);
	assert.strictEqual(overview.routingBusy, false);
	assert.strictEqual(root.children.length, 0);
	assert.strictEqual(fakeWindow.cleared, 17);
	assert.strictEqual(documentElement.attributes['aria-busy'], undefined);
}

testPasswallSelection();
testSimpleState();
testRoutingArguments();
testRoutingContractParity();
testRouteStatusAndProgress();
testExtractedUiHelpers();
testOverviewLoadsAndRendersWithLuCIStateDependency();
testSingleViewMenu();
testClientSideDashboardTabs();
testRoutingBusyOverlayLifecycle();
console.log('Frontend state tests passed.');
