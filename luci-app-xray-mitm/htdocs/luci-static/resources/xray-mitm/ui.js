'use strict';
'require baseclass';
'require ui';
'require xray-mitm.state as state';

function text(value, fallback) {
	if (value === null || value === undefined || value === '')
		return fallback || _('Unknown');

	return String(value);
}

function textNode(value, fallback) {
	return document.createTextNode(text(value, fallback));
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
	return !!(slot && (slot.present === true || slot.fingerprint));
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
		existing: _('Saved rule found (inactive)'),
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

return baseclass.extend({
	assertOk: assertOk,
	decodeRemarks: decodeRemarks,
	notification: notification,
	operationList: operationList,
	optionList: optionList,
	readSelectedFile: readSelectedFile,
	routeStatus: routeStatus,
	routingRuleCard: routingRuleCard,
	selectControl: selectControl,
	setBusy: setBusy,
	simpleCheck: simpleCheck,
	slotData: slotData,
	slotPresent: slotPresent,
	statusPill: statusPill,
	text: text,
	textNode: textNode
});
