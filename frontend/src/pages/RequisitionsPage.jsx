import { useEffect, useState } from "react";
import { apiRequest, apiBlob, apiForm } from "../api/client";
import { getStaffBranchId } from "../api/branchContext";
import {
  isRequisitionsWeb,
  rand,
  saToday,
  lineTotal,
} from "../utils/requisitions";
import "./RequisitionsPage.css";
import {
  REQUISITION_ITEMS,
  paymentDetailLabel,
  selectRequisitionItem,
} from "../utils/requisition-items.mjs";

const emptyLine = () => ({
  category: "",
  description: "",
  method: "eft",
  amount: "",
});
const initialTransaction = () => ({
  requisition_id: "",
  client_key: crypto.randomUUID(),
  transaction_date: saToday(),
  kind: "card",
  supplier: "",
  description: "",
  amount: "",
});

export default function RequisitionsPage({ me }) {
  const [access, setAccess] = useState(null),
    [fid, setFid] = useState(""),
    [branch, setBranch] = useState(""),
    [months, setMonths] = useState([]),
    [mid, setMid] = useState(""),
    [data, setData] = useState(null),
    [books, setBooks] = useState([]),
    [submitted, setSubmitted] = useState([]);
  const [view, setView] = useState("requests"),
    [req, setReq] = useState(null),
    [lines, setLines] = useState([]),
    [details, setDetails] = useState({}),
    [staff, setStaff] = useState([]);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [revision, setRevision] = useState(0),
    [ready, setReady] = useState(false);
  const [monthForm, setMonthForm] = useState({
      month: saToday().slice(0, 7),
      holder: "",
      opening_balance: "0.00",
    }),
    [bookId, setBookId] = useState(""),
    [requestDate, setRequestDate] = useState(saToday()),
    [importFile, setImportFile] = useState(null),
    [tx, setTx] = useState(initialTransaction),
    [receipt, setReceipt] = useState(null),
    [closeConfirm, setCloseConfirm] = useState(false);
  const url = (path, params = {}) =>
    "/requisitions" +
    path +
    "?" +
    new URLSearchParams({
      ...params,
      ...(fid ? { franchise_user_id: fid } : {}),
    });
  const refresh = () => setRevision((x) => x + 1);
  const act = async (fn, message) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
      refresh();
      if (message) setNotice(message);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    let active = true;
    setReady(false);
    setAccess(null);
    apiRequest(url("/access"))
      .then((a) => {
        if (!active) return;
        setAccess(a);
        if (a.enabled && a.branches.length) {
          setBranch((old) =>
            a.branches.some((b) => String(b.id) === old)
              ? old
              : String(
                  a.branches.find(
                    (b) => String(b.id) === String(getStaffBranchId())
                  )?.id || a.branches[0].id
                )
          );
        } else setBranch("");
        setReady(true);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [fid]);
  useEffect(() => {
    let active = true;
    setData(null);
    setBooks([]);
    setSubmitted([]);
    setMonths([]);
    if (!ready || !branch) return;
    Promise.all([
      apiRequest(url("/months", { branch_id: branch })),
      apiRequest(url("/books", { branch_id: branch })),
      apiRequest(url("/submitted", { branch_id: branch })),
    ])
      .then(([m, b, s]) => {
        if (!active) return;
        setMonths(m);
        setBooks(b);
        setSubmitted(s);
        setMid((old) =>
          m.some((x) => String(x.id) === old) ? old : String(m[0]?.id || "")
        );
        setBookId("");
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [branch, fid, ready, revision]);
  useEffect(() => {
    let active = true;
    setData(null);
    setCloseConfirm(false);
    if (!mid || !branch) return;
    apiRequest(url("/months/" + mid))
      .then((d) => {
        if (active && String(d.branch_id) === String(branch)) {
          setData(d);
          setRequestDate(
            d.month === saToday().slice(0, 7) ? saToday() : d.month + "-01"
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [mid, branch, fid, revision]);
  useEffect(() => {
    let active = true;
    if (!access?.can_manage || !branch) return;
    apiRequest(url("/staff"))
      .then((s) => {
        if (active) setStaff(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [access, branch, fid, revision]);
  useEffect(() => {
    if (!branch) return;
    let active = true;
    const sync = () => {
      const id = new URLSearchParams(window.location.search).get("requisition");
      if (!id) {
        setReq(null);
        return;
      }
      apiRequest(url("/requests/" + id))
        .then((r) => {
          if (!active || String(r.branch_id) !== String(branch)) return;
          setMid(String(r.month_id));
          setReq(r);
          setLines(
            r.lines.map((l) => ({
              ...l,
              amount:
                l.amount_cents == null ? "" : (l.amount_cents / 100).toFixed(2),
            }))
          );
          setDetails(r.details);
        })
        .catch((e) => setError(e.message));
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => {
      active = false;
      window.removeEventListener("popstate", sync);
    };
  }, [fid, branch]);
  const openRequest = (r) => {
    setReq(r);
    setLines(
      r.lines.length
        ? r.lines.map((l) => ({
            ...l,
            amount:
              l.amount_cents == null ? "" : (l.amount_cents / 100).toFixed(2),
          }))
        : [emptyLine()]
    );
    setDetails(r.details);
    const u = new URL(window.location.href);
    u.searchParams.set("requisition", r.id);
    window.history.pushState({}, "", u);
  };
  const back = () => {
    setReq(null);
    const u = new URL(window.location.href);
    u.searchParams.delete("requisition");
    window.history.pushState({}, "", u);
    refresh();
  };
  const save = async () => {
    const r = await apiRequest(url("/requests/" + req.id), {
      method: "PUT",
      body: JSON.stringify({
        details,
        expected_revision: req.revision || 0,
        lines: lines.map((l) => ({
          category: l.category || "",
          description: l.description,
          method: l.method,
          amount: l.amount === "" ? null : l.amount,
        })),
      }),
    });
    setReq(r);
    return r;
  };
  const download = async (path, name, params = {}) => {
    const blob = await apiBlob(url(path, params));
    const link = document.createElement("a"),
      href = URL.createObjectURL(blob);
    link.href = href;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  };
  if (!isRequisitionsWeb())
    return <p>Requisitions are available in the desktop web system.</p>;
  if (!access)
    return <p role="status">{error || "Loading requisition access…"}</p>;
  if (!access.enabled)
    return <p>Requisitions access has not been enabled for your account.</p>;
  const selectedBranch = access.branches.find((b) => String(b.id) === branch);
  const locked = data?.status !== "open",
    canEditRequest = req && (req.employee_id === me.id || access.can_manage);
  return (
    <section className="requisitions-page" aria-label="Requisitions">
      <header className="req-heading">
        <div>
          <p className="req-eyebrow">BRANCH FINANCE</p>
          <h1>Requisitions</h1>
          <p>Service requests, card funding and receipt records.</p>
        </div>
        <span className="req-web-badge">Web only</span>
      </header>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="success-message">
          {notice}
        </p>
      )}
      {!access.email_configured && branch && (
        <p className="req-warning">
          Email delivery needs the system’s SMTP connection. Submissions are
          saved and queued; check delivery status below.
        </p>
      )}
      <div className="req-selectors">
        {access.holders.length > 0 && (
          <label>
            Holder group
            <select
              disabled={busy}
              value={fid}
              onChange={(e) => {
                setFid(e.target.value);
                setMid("");
                setBranch("");
                back();
              }}
            >
              <option value="">Select holder group</option>
              {access.holders.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Linked branch
          <select
            disabled={busy || !ready}
            value={branch}
            onChange={(e) => {
              setBranch(e.target.value);
              setMid("");
              back();
            }}
          >
            <option value="">Select branch</option>
            {access.branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Monthly register
          <select
            disabled={busy}
            value={mid}
            onChange={(e) => {
              setMid(e.target.value);
              back();
            }}
          >
            <option value="">Select month</option>
            {months.map((m) => (
              <option key={m.id} value={m.id}>
                {m.month} · {m.status}
              </option>
            ))}
          </select>
        </label>
      </div>
      {branch && (
        <>
          <nav className="req-tabs" aria-label="Requisition sections">
            {[
              ["requests", "Requisitions"],
              ["ledger", "Card transactions"],
              ["setup", "Books & monthly setup"],
              ...(access.can_manage ? [["access", "Staff access"]] : []),
            ].map(([id, label]) => (
              <button
                type="button"
                disabled={busy}
                className={view === id ? "active" : ""}
                key={id}
                onClick={() => {
                  setView(id);
                  back();
                }}
              >
                {label}
              </button>
            ))}
          </nav>
          {data && (
            <div className="req-summary">
              <article>
                <span>Opening balance</span>
                <strong>{rand(data.opening_cents)}</strong>
              </article>
              <article>
                <span>Card balance</span>
                <strong>{rand(data.balance_cents)}</strong>
              </article>
              <article>
                <span>
                  {selectedBranch?.name} · {data.month}
                </span>
                <strong>
                  {data.status === "closed" ? "Month closed" : data.holder}
                </strong>
              </article>
            </div>
          )}
          {view === "setup" && (
            <>
              <section className="form-card">
                <h2>Import Mortuary Book</h2>
                <p>
                  Upload the original PDF for {selectedBranch?.name}. All pages
                  must match this branch; MF file numbers and deceased details
                  will be available on the requisition form.
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    act(async () => {
                      const f = new FormData();
                      f.append("file", importFile);
                      await apiForm(
                        url("/books/import", { branch_id: branch }),
                        f
                      );
                      setImportFile(null);
                      e.target.reset();
                    }, "Mortuary Book imported.");
                  }}
                >
                  <label>
                    Mortuary Book PDF
                    <input
                      required
                      type="file"
                      accept="application/pdf"
                      onChange={(e) => setImportFile(e.target.files[0])}
                    />
                  </label>
                  <button disabled={busy || !importFile}>Import book</button>
                </form>
                <p>{books.length} MF files available.</p>
              </section>
              {access.can_manage && (
                <section className="form-card">
                  <h2>New monthly register</h2>
                  <p>
                    Close the previous month first. Its closing balance will
                    carry into the next month automatically. Enter an opening
                    balance only for the first register.
                  </p>
                  <form
                    className="req-form-grid"
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(async () => {
                        const r = await apiRequest(url("/months"), {
                          method: "POST",
                          body: JSON.stringify({
                            ...monthForm,
                            branch_id: Number(branch),
                          }),
                        });
                        setMid(String(r.id));
                        setView("ledger");
                      }, "Monthly register created.");
                    }}
                  >
                    <label>
                      Month
                      <input
                        required
                        type="month"
                        value={monthForm.month}
                        onChange={(e) =>
                          setMonthForm({ ...monthForm, month: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Card holder
                      <input
                        required
                        maxLength={255}
                        value={monthForm.holder}
                        onChange={(e) =>
                          setMonthForm({ ...monthForm, holder: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Initial opening balance (ZAR)
                      <input
                        disabled={months.length > 0}
                        type="number"
                        step="0.01"
                        value={monthForm.opening_balance}
                        onChange={(e) =>
                          setMonthForm({
                            ...monthForm,
                            opening_balance: e.target.value,
                          })
                        }
                      />
                    </label>
                    <button disabled={busy}>Create monthly register</button>
                  </form>
                </section>
              )}
              {data && (
                <section className="form-card">
                  <h2>Branch files</h2>
                  <p>
                    Stored under Requisitions / {selectedBranch?.name} /{" "}
                    {data.month}. Download the blank form for reuse or the
                    latest completed workbook.
                  </p>
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(() =>
                        download("/months/" + mid + "/workbook", "blank.xlsx", {
                          blank: true,
                        })
                      )
                    }
                  >
                    Download blank workbook
                  </button>{" "}
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(() =>
                        download(
                          "/months/" + mid + "/workbook",
                          "card-transactions.xlsx"
                        )
                      )
                    }
                  >
                    Download current workbook
                  </button>
                </section>
              )}
            </>
          )}
          {view === "access" && access.can_manage && (
            <section className="form-card">
              <h2>Selected staff</h2>
              <p>
                Enabled employees and managers can create requests and view all
                linked branches in this holder group. Funding, EFT posting and
                access management remain with the holder and administrator.
              </p>
              {staff.map((s) => (
                <label className="req-grant" key={s.id}>
                  <input
                    type="checkbox"
                    checked={s.enabled}
                    disabled={busy}
                    onChange={(e) =>
                      act(
                        () =>
                          apiRequest(url("/grants"), {
                            method: "PUT",
                            body: JSON.stringify({
                              user_id: s.id,
                              enabled: e.target.checked,
                            }),
                          }),
                        "Staff access updated."
                      )
                    }
                  />
                  {s.full_name}
                </label>
              ))}
            </section>
          )}
          {view === "requests" && !req && (
            <>
              {data && !locked && (
                <section className="form-card">
                  <h2>New service requisition</h2>
                  <form
                    className="req-form-grid"
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(async () => {
                        const r = await apiRequest(url("/requests"), {
                          method: "POST",
                          body: JSON.stringify({
                            month_id: Number(mid),
                            book_id: Number(bookId),
                            request_date: requestDate,
                          }),
                        });
                        openRequest(r);
                      });
                    }}
                  >
                    <label>
                      MF file and deceased
                      <select
                        required
                        value={bookId}
                        onChange={(e) => setBookId(e.target.value)}
                      >
                        <option value="">Select an imported MF file</option>
                        {books.map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.reference} · {b.deceased}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Requisition date
                      <input
                        type="date"
                        required
                        value={requestDate}
                        onChange={(e) => setRequestDate(e.target.value)}
                      />
                    </label>
                    <label>
                      Employee
                      <input readOnly value={me.full_name} />
                    </label>
                    <button disabled={busy || !bookId}>
                      Create & enter payments
                    </button>
                  </form>
                  {!books.length && (
                    <p>
                      Import the Mortuary Book under Books & monthly setup
                      first.
                    </p>
                  )}
                </section>
              )}
              {!data && (
                <p>
                  Select a monthly register. The holder can create one under
                  Books & monthly setup.
                </p>
              )}
              {data && (
                <section className="form-card">
                  <h2>Requisition files · {selectedBranch?.name}</h2>
                  {!data.requisitions.length ? (
                    <p>No requisitions for this month.</p>
                  ) : (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Requisition</th>
                            <th>MF file / deceased</th>
                            <th>Employee / date</th>
                            <th>Total requested</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.requisitions.map((r) => (
                            <tr key={r.id}>
                              <td>
                                <button onClick={() => openRequest(r)}>
                                  {r.number || `Draft #${r.id}`}
                                </button>
                              </td>
                              <td>
                                {r.reference}
                                <br />
                                {r.deceased}
                              </td>
                              <td>
                                {r.employee_name}
                                <br />
                                {r.request_date}
                              </td>
                              <td>{rand(r.total_cents)}</td>
                              <td>{r.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
          {view === "requests" && req && (
            <section className="form-card">
              <button disabled={busy} onClick={back}>
                ← Back to requisitions
              </button>
              <h2>
                {req.number || `Draft #${req.id}`} · {req.reference}
              </h2>
              <p>
                <strong>{req.deceased}</strong> · {req.employee_name} ·{" "}
                {req.request_date}
              </p>
              <button
                onClick={() =>
                  act(() =>
                    download(
                      "/books/" + req.book_id + "/file",
                      "mortuary-book.pdf"
                    )
                  )
                }
              >
                Original Mortuary Book
              </button>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  act(async () => {
                    const saved = await save();
                    setNotice(
                      saved.status === "submitted"
                        ? `Revision ${saved.revision} saved. The updated form and register are queued for email.`
                        : "Draft saved."
                    );
                  });
                }}
              >
                <fieldset disabled={!canEditRequest || busy}>
                  <legend>Deceased and service details</legend>
                  <div className="req-form-grid">
                    {[
                      ...new Set([
                        ...Object.keys(details),
                        "date_of_death",
                        "funeral_date",
                        "service_required",
                        "service_venue",
                        "coffin_casket",
                        "additional_details",
                      ]),
                    ].map((key) => (
                      <label key={key}>
                        {{
                          id_number: "Deceased ID number",
                          date_of_death: "Date of death",
                          funeral_date: "Date of service",
                          service_required: "Service required",
                        }[key] || key.replaceAll("_", " ")}
                        <input
                          maxLength={1000}
                          type={
                            ["date_of_death", "funeral_date"].includes(key)
                              ? "date"
                              : "text"
                          }
                          value={details[key] || ""}
                          onChange={(e) =>
                            setDetails({ ...details, [key]: e.target.value })
                          }
                        />
                      </label>
                    ))}
                  </div>
                </fieldset>
                <h3>Payments requested</h3>
                <p>
                  List EFT, cash and card requests together. They are grouped by
                  payment method in the submitted form.
                </p>
                <fieldset disabled={!canEditRequest || busy}>
                  <legend>Payment items</legend>
                  {lines.map((line, i) => (
                    <div className="req-payment-row" key={i}>
                      <label>
                        Payment item
                        <select
                          required={Number(line.amount) > 0}
                          value={line.category || ""}
                          onChange={(e) =>
                            setLines(
                              lines.map((l, j) =>
                                i === j
                                  ? selectRequisitionItem(l, e.target.value)
                                  : l
                              )
                            )
                          }
                        >
                          <option value="">Choose an item</option>
                          {line.category &&
                            !REQUISITION_ITEMS.includes(line.category) && (
                              <option value={line.category}>
                                {line.category}
                              </option>
                            )}
                          {REQUISITION_ITEMS.map((item) => (
                            <option key={item} value={item}>
                              {item}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {paymentDetailLabel(line.category)}
                        <input
                          required={Number(line.amount) > 0}
                          maxLength={1000}
                          value={line.description}
                          onChange={(e) =>
                            setLines(
                              lines.map((l, j) =>
                                i === j
                                  ? { ...l, description: e.target.value }
                                  : l
                              )
                            )
                          }
                        />
                      </label>
                      <label>
                        Method
                        <select
                          value={line.method}
                          onChange={(e) =>
                            setLines(
                              lines.map((l, j) =>
                                i === j ? { ...l, method: e.target.value } : l
                              )
                            )
                          }
                        >
                          <option value="eft">EFT</option>
                          <option value="cash">Cash</option>
                          <option value="card">Card</option>
                        </select>
                      </label>
                      <label>
                        Amount (ZAR)
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          max="10000000"
                          value={line.amount}
                          onChange={(e) =>
                            setLines(
                              lines.map((l, j) =>
                                i === j ? { ...l, amount: e.target.value } : l
                              )
                            )
                          }
                        />
                      </label>
                      <button
                        type="button"
                        aria-label={"Remove payment " + (i + 1)}
                        onClick={() =>
                          setLines(lines.filter((_, j) => i !== j))
                        }
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  {canEditRequest && (
                    <button
                      type="button"
                      disabled={lines.length >= 100}
                      onClick={() => setLines([...lines, emptyLine()])}
                    >
                      + Add payment
                    </button>
                  )}
                </fieldset>
                <div className="req-total">
                  <span>Total requested</span>
                  <strong>{rand(lineTotal(lines))}</strong>
                </div>
                <p>
                  Only items with an amount greater than zero appear in the
                  emailed PDF. Unpriced items stay here so you can complete them
                  later.
                </p>
                {canEditRequest ? (
                  <div className="req-actions">
                    <button
                      disabled={
                        busy ||
                        (req.status === "submitted" && lineTotal(lines) <= 0)
                      }
                    >
                      {req.status === "draft"
                        ? "Save draft"
                        : "Save changes & email revision"}
                    </button>
                    {req.status === "draft" && (
                      <>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            act(async () => {
                              await apiRequest(url("/requests/" + req.id), {
                                method: "DELETE",
                              });
                              back();
                            }, "Draft discarded.")
                          }
                        >
                          Discard draft
                        </button>
                        <button
                          type="button"
                          disabled={busy || lineTotal(lines) <= 0}
                          onClick={(e) => {
                            if (!e.currentTarget.form.reportValidity()) return;
                            act(async () => {
                              await save();
                              const result = await apiRequest(
                                url("/requests/" + req.id + "/submit"),
                                { method: "POST" }
                              );
                              setReq(result);
                              setNotice(
                                "Submitted. The requisition and updated monthly register are queued for wjm@martinsdirect.com."
                              );
                            });
                          }}
                        >
                          Submit & email
                        </button>
                      </>
                    )}
                  </div>
                ) : (
                  <p>
                    Only the employee who created this form or the holder can
                    edit it.
                  </p>
                )}
                {req.status === "submitted" && (
                  <p>
                    Revision {req.revision || 1}. Saving changes retains this
                    REQ number and emails the revised form. Recorded payments
                    and closed balances remain in the ledger.
                  </p>
                )}
              </form>
              <button
                disabled={busy}
                onClick={() =>
                  act(() =>
                    download("/requests/" + req.id + "/pdf", "requisition.pdf")
                  )
                }
              >
                Download requisition PDF
              </button>
            </section>
          )}
          {view === "ledger" && data && (
            <>
              <section className="form-card">
                <div className="req-section-heading">
                  <h2>Card transactions · {data.month}</h2>
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(() =>
                        download(
                          "/months/" + mid + "/workbook",
                          "card-transactions.xlsx"
                        )
                      )
                    }
                  >
                    Download workbook
                  </button>
                </div>
                <p>
                  Card balance = opening balance + confirmed funding − card
                  purchases − EFT payments. Cash is recorded separately.
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Type / employee</th>
                        <th>Supplier / description</th>
                        <th>Rek. No</th>
                        <th>Reimbursement</th>
                        <th>Card transaction</th>
                        <th>EFT</th>
                        <th>Cash</th>
                        <th>Card balance</th>
                        <th>Proof</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td colSpan={8}>Brought forward from last month</td>
                        <td>{rand(data.opening_cents)}</td>
                        <td />
                      </tr>
                      {data.transactions.map((t) => (
                        <tr key={t.id}>
                          <td>{t.transaction_date}</td>
                          <td>
                            {t.kind}
                            <br />
                            {t.actor_name}
                          </td>
                          <td>
                            {t.supplier}
                            <br />
                            {t.description}
                          </td>
                          <td>{t.number}</td>
                          {["funding", "card", "eft", "cash"].map((k) => (
                            <td key={k}>
                              {t.kind === k ? rand(t.amount_cents) : "—"}
                            </td>
                          ))}
                          <td>{rand(t.balance_cents)}</td>
                          <td>
                            <button
                              onClick={() =>
                                act(() =>
                                  download(
                                    "/transactions/" + t.id + "/receipt",
                                    t.receipt_name
                                  )
                                )
                              }
                            >
                              Receipt
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              {!locked && (
                <section className="form-card">
                  <h2>Record funding or spending</h2>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      act(async () => {
                        const f = new FormData();
                        f.append(
                          "payload",
                          JSON.stringify({
                            ...tx,
                            requisition_id: Number(tx.requisition_id),
                          })
                        );
                        f.append("receipt", receipt);
                        await apiForm(url("/transactions"), f);
                        setTx(initialTransaction());
                        setReceipt(null);
                        e.target.reset();
                      }, "Transaction saved with proof. The updated register is queued for email.");
                    }}
                  >
                    <div className="req-form-grid">
                      <label>
                        Requisition
                        <select
                          required
                          value={tx.requisition_id}
                          onChange={(e) =>
                            setTx({ ...tx, requisition_id: e.target.value })
                          }
                        >
                          <option value="">Select submitted application</option>
                          {submitted.map((r) => (
                            <option value={r.id} key={r.id}>
                              {r.number} · {r.reference}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Transaction date
                        <input
                          required
                          type="date"
                          value={tx.transaction_date}
                          onChange={(e) =>
                            setTx({ ...tx, transaction_date: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Transaction type
                        <select
                          value={tx.kind}
                          onChange={(e) =>
                            setTx({ ...tx, kind: e.target.value })
                          }
                        >
                          <option value="card">Card purchase</option>
                          <option value="cash">Cash payment</option>
                          {access.can_manage && (
                            <>
                              <option value="funding">
                                Card funding / reimbursement
                              </option>
                              <option value="eft">EFT payment</option>
                            </>
                          )}
                        </select>
                      </label>
                      <label>
                        Supplier / payee
                        <input
                          required
                          maxLength={255}
                          value={tx.supplier}
                          onChange={(e) =>
                            setTx({ ...tx, supplier: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Service / product description
                        <input
                          required
                          maxLength={1000}
                          value={tx.description}
                          onChange={(e) =>
                            setTx({ ...tx, description: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Exact amount (ZAR)
                        <input
                          required
                          type="number"
                          min="0.01"
                          step="0.01"
                          max="10000000"
                          value={tx.amount}
                          onChange={(e) =>
                            setTx({ ...tx, amount: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Receipt / payment proof
                        <input
                          required
                          type="file"
                          accept="application/pdf,image/png,image/jpeg"
                          onChange={(e) => setReceipt(e.target.files[0])}
                        />
                      </label>
                    </div>
                    <button disabled={busy || !receipt}>
                      Save transaction & email register
                    </button>
                  </form>
                </section>
              )}
              {access.can_manage && !locked && (
                <section className="form-card">
                  <h2>Close monthly register</h2>
                  <p>
                    Closure locks transactions and requisitions. The closing
                    card balance will carry forward to the new month.
                  </p>
                  <label className="req-grant">
                    <input
                      type="checkbox"
                      checked={closeConfirm}
                      onChange={(e) => setCloseConfirm(e.target.checked)}
                    />
                    I have checked the receipts and closing balance.
                  </label>
                  <button
                    disabled={busy || !closeConfirm}
                    onClick={() =>
                      act(
                        () =>
                          apiRequest(url("/months/" + mid + "/close"), {
                            method: "POST",
                          }),
                        "Month closed and final register queued for email."
                      )
                    }
                  >
                    Close month
                  </button>
                </section>
              )}
            </>
          )}
          {data && (
            <section className="form-card req-delivery">
              <h2>Email delivery</h2>
              <p>
                Recipient: wjm@martinsdirect.com. Each submission and
                transaction queues the updated monthly file.
              </p>
              <button disabled={busy} onClick={refresh}>
                Refresh status
              </button>
              {!data.emails.length ? (
                <p>No emails queued for this month.</p>
              ) : (
                <ul>
                  {data.emails.map((e) => (
                    <li key={e.id}>
                      <strong>{e.subject}</strong>
                      <span>
                        {e.status}
                        {e.sent_at ? " · " + e.sent_at : ""}
                      </span>
                      {e.error && <p>{e.error}</p>}
                      {access.can_manage &&
                        ["pending", "failed"].includes(e.status) && (
                          <button
                            disabled={busy}
                            onClick={() =>
                              act(
                                () =>
                                  apiRequest(
                                    url("/emails/" + e.id + "/retry"),
                                    { method: "POST" }
                                  ),
                                "Email retry queued."
                              )
                            }
                          >
                            Retry delivery
                          </button>
                        )}
                      {["sending", "uncertain"].includes(e.status) && (
                        <p>
                          Check mailbox delivery before resending this item.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </>
      )}
    </section>
  );
}
