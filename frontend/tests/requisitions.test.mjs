import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import React from "react";
import * as jsxRuntime from "react/jsx-runtime";
import TestRenderer, { act } from "react-test-renderer";
import { transformSync } from "esbuild";

const compiled = transformSync(
  fs.readFileSync(
    new URL("../src/pages/RequisitionsPage.jsx", import.meta.url),
    "utf8"
  ),
  { loader: "jsx", format: "cjs", jsx: "automatic" }
).code;
const text = (node) =>
  typeof node === "string" ? node : node?.children?.map(text).join("") || "";
async function mount({ enabled = true, admin = false } = {}) {
  let currentUrl = new URL(
    "https://example.test/?staff_portal_page=requisitions"
  );
  globalThis.window = {
    location: {
      get href() {
        return currentUrl.href;
      },
      get search() {
        return currentUrl.search;
      },
    },
    history: {
      pushState(a, b, url) {
        currentUrl = new URL(url);
      },
    },
    addEventListener() {},
    removeEventListener() {},
  };
  const writes = [],
    module = { exports: {} };
  const draft = {
    id: 11,
    month_id: 1,
    branch_id: 101,
    book_id: 21,
    employee_id: 2,
    employee_name: "Staff",
    request_date: "2026-11-02",
    number: null,
    status: "draft",
    reference: "MF123",
    deceased: "Example Person",
    lines: [],
    details: { id_number: "0000000000000" },
    total_cents: 0,
  };
  const apiRequest = async (path, options) => {
    if (options) {
      writes.push({ path, options });
      if (options.method === "PUT") {
        const payload = JSON.parse(options.body);
        draft.lines = payload.lines.map((l) => ({
          ...l,
          amount_cents: Math.round(Number(l.amount) * 100),
        }));
        draft.total_cents = draft.lines.reduce(
          (sum, l) => sum + l.amount_cents,
          0
        );
        draft.details = payload.details;
      }
      if (path.includes("/submit")) {
        draft.number = "REQ-101-2026-000011";
        draft.status = "submitted";
      }
      return { ...draft };
    }
    if (path.startsWith("/requisitions/access"))
      return {
        enabled,
        can_manage: admin,
        holders: [],
        branches: [
          { id: 101, name: "Northcliff" },
          { id: 102, name: "Rivonia" },
        ],
        email_configured: true,
      };
    if (path.startsWith("/requisitions/months?"))
      return [{ id: 1, month: "2026-11", holder: "Holder", status: "open" }];
    if (path.startsWith("/requisitions/months/"))
      return {
        id: 1,
        month: "2026-11",
        branch_id: 101,
        holder: "Holder",
        status: "open",
        opening_cents: 50000,
        balance_cents: 50000,
        requisitions: [{ ...draft }],
        transactions: [],
        emails: [],
      };
    if (path.startsWith("/requisitions/books?"))
      return [{ id: 21, reference: "MF123", deceased: "Example Person" }];
    if (path.startsWith("/requisitions/submitted")) return [];
    if (path.startsWith("/requisitions/staff"))
      return [{ id: 2, full_name: "Staff", enabled: true }];
    throw new Error(path);
  };
  new Function("require", "module", "exports", compiled)(
    (name) => {
      if (name === "react") return React;
      if (name === "react/jsx-runtime") return jsxRuntime;
      if (name === "../api/client")
        return {
          apiRequest,
          apiBlob: async () => new Blob(),
          apiForm: async () => ({}),
        };
      if (name === "../api/branchContext")
        return { getStaffBranchId: () => 101 };
      if (name === "../utils/requisitions")
        return {
          isRequisitionsWeb: () => true,
          saToday: () => "2026-11-02",
          rand: (c) => `R ${(Number(c || 0) / 100).toFixed(2)}`,
          lineTotal: (lines) =>
            lines.reduce(
              (sum, l) => sum + Math.round(Number(l.amount || 0) * 100),
              0
            ),
        };
      if (name.endsWith(".css")) return {};
      throw new Error(name);
    },
    module,
    module.exports
  );
  let view;
  await act(async () => {
    view = TestRenderer.create(
      React.createElement(module.exports.default, {
        me: { id: 2, full_name: "Staff" },
      })
    );
  });
  return {
    view,
    writes,
    button: (label) =>
      view.root.findAllByType("button").find((b) => text(b) === label),
  };
}

test("selected staff can create an MF request, save without leaving its page, and submit the summed payments", async () => {
  const { view, writes, button } = await mount();
  try {
    const select = view.root
      .findAllByType("select")
      .find((s) =>
        s.findAllByType("option").some((o) => text(o).includes("MF123"))
      );
    act(() => select.props.onChange({ target: { value: "21" } }));
    await act(async () => {
      view.root.findByType("form").props.onSubmit({ preventDefault() {} });
    });
    assert.ok(button("Save draft"));
    assert.match(JSON.stringify(view.toJSON()), /Example Person/);
    const inputs = view.root.findAllByType("input");
    act(() =>
      inputs
        .find((i) => i.props.maxLength === 1000 && !i.props.value)
        .props.onChange({ target: { value: "Cremation" } })
    );
    const amount = view.root
      .findAllByType("input")
      .find((i) => i.props.type === "number");
    act(() => amount.props.onChange({ target: { value: "3250.35" } }));
    await act(async () => {
      view.root.findByType("form").props.onSubmit({ preventDefault() {} });
    });
    assert.ok(button("Save draft"), "refresh must retain the editor");
    assert.match(JSON.stringify(view.toJSON()), /3250.35/);
    await act(async () => {
      button("Submit & email").props.onClick({
        currentTarget: { form: { reportValidity: () => true } },
      });
    });
    assert.equal(writes.filter((w) => w.path.includes("/submit")).length, 1);
    assert.equal(
      JSON.parse(writes.find((w) => w.options.method === "PUT").options.body)
        .lines[0].amount,
      "3250.35"
    );
    assert.equal(button("Save draft"), undefined);
    assert.match(
      JSON.stringify(view.toJSON()),
      /queued for wjm@martinsdirect.com/
    );
  } finally {
    view.unmount();
  }
});

test("ordinary enabled staff see spending but cannot choose funding, EFT, access management or month closure", async () => {
  const { view, button } = await mount();
  try {
    assert.equal(button("Staff access"), undefined);
    await act(async () => button("Card transactions").props.onClick());
    const values = view.root.findAllByType("option").map((o) => o.props.value);
    assert.ok(values.includes("card"));
    assert.ok(values.includes("cash"));
    assert.ok(!values.includes("funding"));
    assert.ok(!values.includes("eft"));
    assert.equal(button("Close month"), undefined);
  } finally {
    view.unmount();
  }
});

test("an account without a requisition grant sees no forms or financial records", async () => {
  const { view } = await mount({ enabled: false });
  try {
    assert.equal(view.root.findAllByType("form").length, 0);
    assert.match(JSON.stringify(view.toJSON()), /not been enabled/);
  } finally {
    view.unmount();
  }
});
