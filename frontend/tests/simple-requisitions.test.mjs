import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import React from 'react';
import * as jsxRuntime from 'react/jsx-runtime';
import TestRenderer, { act } from 'react-test-renderer';
import { transformSync } from 'esbuild';
import * as items from '../src/utils/requisition-items.mjs';
const compiled = transformSync(fs.readFileSync(new URL('../src/pages/SimpleRequisitionsPage.jsx', import.meta.url), 'utf8'), {
  loader: 'jsx',
  format: 'cjs',
  jsx: 'automatic'
}).code;
const text = node => typeof node === 'string' ? node : node?.children?.map(text).join('') || '';
async function mount({
  enabled = true,
  commissionOnly = false,
  multiple = false
} = {}) {
  let currentUrl = new URL('https://example.test/?staff_portal_page=requisitions');
  globalThis.window = {
    location: {
      get href() {
        return currentUrl.href;
      },
      get search() {
        return currentUrl.search;
      }
    },
    history: {
      pushState(a, b, url) {
        currentUrl = new URL(url);
      }
    },
    addEventListener() {},
    removeEventListener() {}
  };
  const writes = [],
    module = {
      exports: {}
    };
  const draft = {
    id: 11,
    month_id: 1,
    branch_id: 102,
    book_id: 21,
    employee_id: 2,
    employee_name: 'Staff',
    request_date: '2026-11-18',
    number: 'REQ-2-2026-000011',
    revision: 0,
    status: 'draft',
    reference: 'MF123',
    deceased: 'Example Person',
    lines: [],
    details: {
      client_name: 'Client Example'
    },
    total_cents: 0
  };
  const imported = [{
    id: 21,
    reference: 'MF123',
    deceased: 'Example Person',
    branch_id: 102,
    branch_name: 'Rivonia'
  }, ...(multiple ? [{
    id: 22,
    reference: 'MF124',
    deceased: 'Second Person',
    branch_id: 101,
    branch_name: 'Northcliff'
  }] : [])];
  const apiRequest = async (path, options) => {
    if (options) {
      writes.push({
        path,
        options
      });
      if (options.method === 'PUT') {
        const body = JSON.parse(options.body);
        draft.lines = body.lines.map(l => ({
          ...l,
          amount_cents: l.amount == null ? null : Math.round(Number(l.amount) * 100)
        }));
        draft.total_cents = draft.lines.reduce((sum, l) => sum + (l.amount_cents || 0), 0);
        draft.details = body.details;
        if (draft.status === 'submitted') draft.revision++;
      }
      if (path.includes('/submit')) {
        draft.status = 'submitted';
        draft.revision = 1;
      }
      return {
        ...draft
      };
    }
    if (path.includes('/access')) return {
      enabled,
      can_manage: false,
      franchise_user_id: 10,
      holders: [],
      branches: [{
        id: 101,
        name: 'Northcliff'
      }, {
        id: 102,
        name: 'Rivonia'
      }]
    };
    if (path.includes('/workflow/requests')) return [];
    if (path.includes('/months?')) return [{
      id: 1,
      month: '2026-11'
    }];
    if (path.includes('/months/')) return {
      id: 1,
      month: '2026-11',
      branch_id: 101,
      opening_cents: 0,
      balance_cents: 10000,
      transactions: []
    };
    if (path.includes('/submitted')) return [{
      ...draft,
      status: 'submitted'
    }];
    if (path.includes('/requests/')) return {
      ...draft
    };
    throw new Error(path);
  };
  new Function('require', 'module', 'exports', compiled)(name => {
    if (name === 'react') return React;
    if (name === 'react/jsx-runtime') return jsxRuntime;
    if (name === '../api/client') return {
      apiRequest,
      apiBlob: async () => new Blob(),
      apiForm: async (path, form) => {
        writes.push({
          path,
          form
        });
        return {
          items: imported
        };
      }
    };
    if (name === '../utils/requisitions') return {
      isRequisitionsWeb: () => true,
      saToday: () => '2026-11-18',
      rand: c => `R ${(Number(c || 0) / 100).toFixed(2)}`,
      lineTotal: lines => lines.reduce((sum, l) => sum + Math.round(Number(l.amount || 0) * 100), 0)
    };
    if (name === '../utils/requisition-items.mjs') return items;
    if (name.endsWith('.css')) return {};
    throw new Error(name);
  }, module, module.exports);
  let view;
  await act(async () => {
    view = TestRenderer.create(React.createElement(commissionOnly ? module.exports.MortuaryBookUpload : module.exports.default, commissionOnly ? {
      commissionOnly: true
    } : {
      me: {
        id: 2
      }
    }));
  });
  const button = label => view.root.findAllByType('button').find(b => text(b) === label);
  const input = label => view.root.findAllByType('label').find(l => text(l).startsWith(label)).findByType('input');
  const select = label => view.root.findAllByType('label').find(l => text(l).startsWith(label)).findByType('select');
  const click = async label => act(async () => button(label).props.onClick());
  const change = (node, value) => act(() => node.props.onChange({
    target: {
      value
    }
  }));
  const submit = async () => act(async () => view.root.findByType('form').props.onSubmit({
    preventDefault() {}
  }));
  const upload = async () => {
    act(() => view.root.findByProps({
      type: 'file'
    }).props.onChange({
      target: {
        files: [new Blob(['pdf'], {
          type: 'application/pdf'
        })]
      }
    }));
    await submit();
  };
  return {
    view,
    writes,
    button,
    input,
    select,
    click,
    change,
    submit,
    upload
  };
}
test('Requisition opens PDF upload and one MF opens its automatically numbered branch form', async () => {
  const ui = await mount();
  try {
    assert.equal(ui.view.root.findAllByType('form').length, 0);
    assert.equal(ui.button('Settings'), undefined);
    await ui.click('Requisition');
    await ui.upload();
    assert.equal(ui.input('REQ number').props.value, 'REQ-2-2026-000011');
    assert.equal(ui.input('Branch').props.value, 'Rivonia');
    assert.equal(ui.input('MF file number').props.value, 'MF123');
    assert.equal(ui.input('Client name').props.value, 'Client Example');
    assert.equal(ui.writes.filter(w => w.path.includes('/workflow/start')).length, 1);
    assert.ok(ui.button('Submit'));
    assert.ok(ui.button('Save draft'));
  } finally {
    ui.view.unmount();
  }
});
test('manual items, amounts and an unpriced row save, submit and remain editable as a revision', async () => {
  const ui = await mount();
  try {
    await ui.click('Requisition');
    await ui.upload();
    assert.deepEqual(ui.select('Item').findAllByType('option').slice(1).map(text), items.REQUISITION_ITEMS);
    ui.change(ui.select('Item'), 'Coffin Type');
    ui.change(ui.input('Coffin type'), 'Oak coffin');
    ui.change(ui.input('Amount (R)'), '3250.35');
    await ui.click('Add item');
    await ui.click('Save draft');
    let saved = JSON.parse(ui.writes.find(w => w.options?.method === 'PUT').options.body);
    assert.equal(saved.lines[0].description, 'Oak coffin');
    assert.equal(saved.lines[0].amount, '3250.35');
    assert.equal(saved.lines[1].amount, null);
    assert.ok(ui.button('Submit'));
    await ui.submit();
    assert.equal(ui.writes.filter(w => w.path.includes('/submit')).length, 1);
    assert.equal(ui.button('Save draft'), undefined);
    assert.ok(ui.button('Save changes and email'));
    ui.change(ui.input('Amount (R)'), '3300.00');
    await ui.submit();
    saved = JSON.parse(ui.writes.filter(w => w.options?.method === 'PUT').at(-1).options.body);
    assert.equal(saved.expected_revision, 1);
    assert.equal(saved.lines[0].amount, '3300.00');
    assert.equal(ui.input('REQ number').props.value, 'REQ-2-2026-000011');
    assert.match(JSON.stringify(ui.view.toJSON()), /revised PDF is queued/);
  } finally {
    ui.view.unmount();
  }
});
test('multi-MF upload requires the employee to select the correct file', async () => {
  const ui = await mount({
    multiple: true
  });
  try {
    await ui.click('Requisition');
    await ui.upload();
    assert.equal(ui.writes.filter(w => w.path.includes('/workflow/start')).length, 0);
    assert.match(JSON.stringify(ui.view.toJSON()), /Select the MF file/);
    await ui.click('Rivonia · MF123 · Example Person');
    assert.equal(ui.input('MF file number').props.value, 'MF123');
  } finally {
    ui.view.unmount();
  }
});
test('staff can record card, EFT and cash with mandatory proof without funding or month setup controls', async () => {
  const ui = await mount();
  try {
    await ui.click('Card transactions');
    assert.deepEqual(ui.select('Payment method').findAllByType('option').map(o => o.props.value), ['card', 'eft', 'cash']);
    assert.equal(ui.input('Receipt / slip').props.required, true);
    assert.equal(ui.input('Amount paid (R)').props.step, '0.01');
    assert.equal(ui.button('Close month'), undefined);
    assert.equal(ui.button('Create month'), undefined);
    assert.match(JSON.stringify(ui.view.toJSON()), /Balance left on card/);
  } finally {
    ui.view.unmount();
  }
});
test('commission-only upload saves evidence without creating or exposing financial forms', async () => {
  const ui = await mount({
    commissionOnly: true
  });
  try {
    await ui.upload();
    assert.match(JSON.stringify(ui.view.toJSON()), /Mortuary book saved for commissions/);
    assert.equal(ui.writes.length, 1);
    assert.match(ui.writes[0].path, /books\/import/);
    assert.equal(ui.button('Submit'), undefined);
  } finally {
    ui.view.unmount();
  }
});
test('an unselected account sees no requisition form or records', async () => {
  const ui = await mount({
    enabled: false
  });
  try {
    assert.equal(ui.button('Requisition'), undefined);
    assert.equal(ui.view.root.findAllByType('form').length, 0);
  } finally {
    ui.view.unmount();
  }
});
