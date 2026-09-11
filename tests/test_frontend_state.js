'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const modulePath = path.join(__dirname, '..', 'luci-app-xray-mitm', 'htdocs',
	'luci-static', 'resources', 'xray-mitm', 'state.js');
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

testPasswallSelection();
testSimpleState();
testRoutingArguments();
testRouteStatusAndProgress();
console.log('Frontend state tests passed.');
