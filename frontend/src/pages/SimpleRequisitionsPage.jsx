import { useEffect, useState } from 'react';
import { apiRequest, apiBlob, apiForm } from '../api/client';
import { isRequisitionsWeb, rand, saToday, lineTotal } from '../utils/requisitions';
import { REQUISITION_ITEMS, paymentDetailLabel, selectRequisitionItem } from '../utils/requisition-items.mjs';
import './RequisitionsPage.css';
import './SimpleRequisitionsPage.css';
const emptyLine = () => ({
  category: '',
  description: '',
  method: 'card',
  amount: ''
});
const emptyPayment = () => ({
  requisition_id: '',
  client_key: crypto.randomUUID(),
  transaction_date: saToday(),
  kind: 'card',
  supplier: '',
  description: '',
  amount: ''
});
export function MortuaryBookUpload({
  url = path => '/requisitions' + path,
  onImported,
  commissionOnly = false
}) {
  const [file, setFile] = useState(null),
    [items, setItems] = useState([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [done, setDone] = useState(false);
  const upload = async event => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await apiForm(url('/books/import'), form);
      if (commissionOnly) {
        setDone(true);
        setItems(result.items);
      } else if (result.items.length === 1) await onImported(result.items[0]);else setItems(result.items);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const choose = async item => {
    setBusy(true);
    setError('');
    try {
      await onImported(item);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return <section className="form-card"><h2>Upload mortuary book</h2>
    {error && <p role="alert">{error}</p>}
    {done ? <><p role="status">Mortuary book saved for commissions.</p>{items.map(item => <p key={item.id}>{item.branch_name} · {item.reference} · {item.deceased}</p>)}</> : items.length ? <><p>Select the MF file for this requisition.</p>{items.map(item => <p key={item.id}><button disabled={busy} onClick={() => choose(item)}>{item.branch_name} · {item.reference} · {item.deceased}</button></p>)}</> : <form onSubmit={upload}><label>Mortuary book PDF<input required type="file" accept="application/pdf,.pdf" disabled={busy} onChange={event => setFile(event.target.files[0] || null)} /></label><p><button disabled={busy || !file} type="submit">{busy ? 'Uploading…' : 'Upload'}</button></p></form>}
  </section>;
}
export default function SimpleRequisitionsPage({
  me
}) {
  const [access, setAccess] = useState(null),
    [fid, setFid] = useState(''),
    [view, setView] = useState('home'),
    [requests, setRequests] = useState([]);
  const [req, setReq] = useState(null),
    [lines, setLines] = useState([]),
    [details, setDetails] = useState({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [branch, setBranch] = useState(''),
    [months, setMonths] = useState([]),
    [mid, setMid] = useState(''),
    [ledger, setLedger] = useState(null),
    [submitted, setSubmitted] = useState([]),
    [payment, setPayment] = useState(emptyPayment),
    [receipt, setReceipt] = useState(null);
  const [staff, setStaff] = useState([]),
    [recipient, setRecipient] = useState(''),
    [tick, setTick] = useState(0);
  const url = (path, params = {}) => '/requisitions' + path + '?' + new URLSearchParams({
    ...params,
    ...(fid ? {
      franchise_user_id: fid
    } : {})
  });
  const refresh = () => setTick(value => value + 1);
  const act = async (fn, message) => {
    setBusy(true);
    setError('');
    setNotice('');
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
  const open = r => {
    setReq(r);
    setLines(r.lines.length ? r.lines.map(line => ({
      ...line,
      amount: line.amount_cents == null ? '' : (line.amount_cents / 100).toFixed(2)
    })) : [emptyLine()]);
    setDetails(r.details);
    setView('form');
    const u = new URL(window.location.href);
    u.searchParams.set('requisition', r.id);
    window.history.pushState({}, '', u);
  };
  const back = () => {
    setReq(null);
    setView('home');
    setError('');
    const u = new URL(window.location.href);
    u.searchParams.delete('requisition');
    window.history.pushState({}, '', u);
    refresh();
  };
  useEffect(() => {
    let active = true;
    setAccess(null);
    setReq(null);
    setView('home');
    apiRequest(url('/access')).then(a => {
      if (active) {
        setAccess(a);
        setBranch(String(a.branches[0]?.id || ''));
      }
    }).catch(e => {
      if (active) setError(e.message);
    });
    return () => {
      active = false;
    };
  }, [fid, me.id]);
  useEffect(() => {
    if (!access?.enabled || !access.franchise_user_id) return;
    let active = true;
    apiRequest(url('/workflow/requests')).then(r => {
      if (active) setRequests(r);
    }).catch(e => {
      if (active) setError(e.message);
    });
    return () => {
      active = false;
    };
  }, [access, tick]);
  useEffect(() => {
    if (!access?.franchise_user_id) return;
    let active = true;
    const sync = () => {
      const id = new URLSearchParams(window.location.search).get('requisition');
      if (!id) {
        setReq(null);
        setView('home');
        return;
      }
      apiRequest(url('/requests/' + id)).then(r => {
        if (active) {
          setReq(r);
          setLines(r.lines.length ? r.lines.map(l => ({
            ...l,
            amount: l.amount_cents == null ? '' : (l.amount_cents / 100).toFixed(2)
          })) : [emptyLine()]);
          setDetails(r.details);
          setView('form');
        }
      }).catch(e => {
        if (active) setError(e.message);
      });
    };
    sync();
    window.addEventListener('popstate', sync);
    return () => {
      active = false;
      window.removeEventListener('popstate', sync);
    };
  }, [access]);
  useEffect(() => {
    if (view !== 'card' || !branch) return;
    let active = true;
    setLedger(null);
    Promise.all([apiRequest(url('/months', {
      branch_id: branch
    })), apiRequest(url('/submitted', {
      branch_id: branch
    }))]).then(([m, s]) => {
      if (active) {
        setMonths(m);
        setSubmitted(s);
        setMid(old => m.some(x => String(x.id) === old) ? old : String(m[0]?.id || ''));
      }
    }).catch(e => {
      if (active) setError(e.message);
    });
    return () => {
      active = false;
    };
  }, [view, branch, tick, fid]);
  useEffect(() => {
    if (view !== 'card' || !mid) return;
    let active = true;
    setLedger(null);
    apiRequest(url('/months/' + mid)).then(d => {
      if (active && String(d.branch_id) === branch) setLedger(d);
    }).catch(e => {
      if (active) setError(e.message);
    });
    return () => {
      active = false;
    };
  }, [view, branch, mid, tick, fid]);
  useEffect(() => {
    if (view !== 'settings' || !access?.can_manage) return;
    let active = true;
    Promise.all([apiRequest(url('/staff')), apiRequest(url('/report-settings'))]).then(([s, r]) => {
      if (active) {
        setStaff(s);
        setRecipient(r.recipient);
      }
    }).catch(e => {
      if (active) setError(e.message);
    });
    return () => {
      active = false;
    };
  }, [view, access, tick]);
  const save = async () => {
    const r = await apiRequest(url('/requests/' + req.id), {
      method: 'PUT',
      body: JSON.stringify({
        details,
        expected_revision: req.revision,
        lines: lines.map(l => ({
          category: l.category,
          description: l.description,
          method: l.method,
          amount: l.amount === '' ? null : l.amount
        }))
      })
    });
    setReq(r);
    return r;
  };
  const download = async (path, name) => {
    const blob = await apiBlob(url(path));
    const href = URL.createObjectURL(blob),
      a = document.createElement('a');
    a.href = href;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
  };
  const changeLine = (index, patch) => setLines(old => old.map((line, i) => i === index ? {
    ...line,
    ...patch
  } : line));
  if (!isRequisitionsWeb()) return <p>Requisitions are available in the desktop web system.</p>;
  if (!access) return <p role="status">{error || 'Loading…'}</p>;
  if (!access.enabled) return <p>Requisition access has not been enabled for your account.</p>;
  const branchName = id => access.branches.find(b => b.id === Number(id))?.name || '';
  const editable = req && (req.employee_id === me.id || access.can_manage);
  return <section className="requisitions-page req-simple" aria-label="Requisitions">
    <header className="req-heading"><h1>{view === 'form' ? 'Requisition form' : view === 'upload' ? 'New requisition' : view === 'card' ? 'Card transactions' : view === 'settings' ? 'Requisition settings' : 'Requisitions'}</h1>{view !== 'home' && <button disabled={busy} onClick={back}>Back</button>}</header>
    {access.holders?.length > 0 && <label>Holder group<select disabled={busy} value={fid} onChange={e => setFid(e.target.value)}><option value="">Select holder</option>{access.holders.map(h => <option key={h.id} value={h.id}>{h.name}</option>)}</select></label>}
    {error && <p className="error-message" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {view === 'home' && access.franchise_user_id && <>
      <nav className="req-simple-actions"><button onClick={() => {
          setNotice('');
          setView('upload');
        }}>Requisition</button><button onClick={() => setView('card')}>Card transactions</button>{access.can_manage && <button onClick={() => setView('settings')}>Settings</button>}</nav>
      {requests.length ? <div className="req-table-wrap"><table><thead><tr><th>Requisition</th><th>Branch</th><th>MF file</th><th>Deceased</th><th>Total</th><th>Status</th><th></th></tr></thead><tbody>{requests.map(r => <tr key={r.id}><td>{r.number}</td><td>{branchName(r.branch_id)}</td><td>{r.reference}</td><td>{r.deceased}</td><td>{rand(r.total_cents)}</td><td>{r.status}</td><td><button onClick={() => act(async () => open(await apiRequest(url('/requests/' + r.id))))}>Open</button></td></tr>)}</tbody></table></div> : <p>No requisitions yet.</p>}
    </>}
    {view === 'upload' && <MortuaryBookUpload url={url} onImported={async item => open(await apiRequest(url('/workflow/start'), {
      method: 'POST',
      body: JSON.stringify({
        book_id: item.id
      })
    }))} />}
    {view === 'form' && req && <form onSubmit={e => {
      e.preventDefault();
      act(async () => {
        const r = await save();
        if (r.status === 'draft') setReq(await apiRequest(url('/requests/' + r.id + '/submit'), {
          method: 'POST'
        }));
      }, req.status === 'submitted' ? 'Changes saved. The revised PDF is queued for email.' : 'Submitted. The PDF is queued for email to wjm@martinsdirect.com.');
    }}>
      <fieldset disabled={busy || !editable}>
        <section className="form-card"><div className="req-form-grid">{[['REQ number', req.number], ['Date', req.request_date], ['Branch', branchName(req.branch_id)], ['Employee', req.employee_name], ['MF file number', req.reference], ['Deceased name and surname', req.deceased]].map(([label, value]) => <label key={label}>{label}<input readOnly value={value || ''} /></label>)}</div>
          <div className="req-form-grid">{[['client_name', 'Client name'], ['client_contact_number', 'Client contact number'], ['client_address', 'Client address'], ['id_number', 'Deceased ID number'], ['date_of_death', 'Date of death'], ['funeral_date', 'Funeral date'], ['service_required', 'Service required']].map(([key, label]) => <label key={key}>{label}<input type={key === 'date_of_death' || key === 'funeral_date' ? 'date' : 'text'} maxLength={1000} value={details[key] || ''} onChange={e => setDetails({
                ...details,
                [key]: e.target.value
              })} /></label>)}</div>
        </section>
        <section className="form-card"><h2>Items and amounts</h2>{lines.map((line, index) => <div className="req-simple-line" key={index}>
          <label>Item<select value={line.category} onChange={e => changeLine(index, selectRequisitionItem(line, e.target.value))}><option value="">Choose item</option>{REQUISITION_ITEMS.map(item => <option key={item}>{item}</option>)}</select></label>
          <label>{paymentDetailLabel(line.category)}<input maxLength={1000} value={line.description} onChange={e => changeLine(index, {
                description: e.target.value
              })} /></label>
          <label>Payment method<select value={line.method} onChange={e => changeLine(index, {
                method: e.target.value
              })}><option value="card">Card</option><option value="eft">EFT</option><option value="cash">Cash</option></select></label>
          <label>Amount (R)<input type="number" min="0" max="10000000" step="0.01" value={line.amount} onChange={e => changeLine(index, {
                amount: e.target.value
              })} /></label>
          <button type="button" aria-label={'Remove item ' + (index + 1)} onClick={() => setLines(old => old.filter((_, i) => i !== index))}>Remove</button>
        </div>)}<button type="button" onClick={() => setLines(old => [...old, emptyLine()])}>Add item</button><div className="req-total"><span>Total</span><strong>{rand(lineTotal(lines))}</strong></div>
          <p>Only items with an amount greater than zero appear on the PDF.</p>
          <div className="req-simple-actions">{req.status === 'draft' && <button type="button" onClick={() => act(save, 'Draft saved.')}>Save draft</button>}<button type="submit">{busy ? 'Saving…' : req.status === 'submitted' ? 'Save changes and email' : 'Submit'}</button></div>
        </section>
      </fieldset>
      <button type="button" disabled={busy} onClick={() => act(() => download('/requests/' + req.id + '/pdf', req.number + '.pdf'))}>View PDF</button>
    </form>}
    {view === 'card' && <>
      <div className="req-selectors"><label>Branch<select value={branch} onChange={e => {
            setBranch(e.target.value);
            setMid('');
            setPayment(emptyPayment());
          }}>{access.branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label><label>Month<select value={mid} onChange={e => setMid(e.target.value)}><option value="">Select month</option>{months.map(m => <option key={m.id} value={m.id}>{m.month}</option>)}</select></label></div>
      {ledger ? <><div className="req-total"><span>Balance left on card</span><strong>{rand(ledger.balance_cents)}</strong></div><button disabled={busy} onClick={() => act(() => download('/months/' + mid + '/workbook', 'card-transactions-' + ledger.month + '.xlsx'))}>Download card transactions</button>
        <div className="req-table-wrap"><table><thead><tr><th>Date</th><th>REQ number</th><th>Supplier / details</th><th>Added</th><th>Paid</th><th>Balance</th><th>Proof</th></tr></thead><tbody><tr><td colSpan="5">Brought forward</td><td>{rand(ledger.opening_cents)}</td><td></td></tr>{ledger.transactions.map(t => <tr key={t.id}><td>{t.transaction_date}</td><td>{t.number}</td><td>{t.supplier}<br />{t.description}</td><td>{['allocation', 'funding'].includes(t.kind) ? rand(t.amount_cents) : ''}</td><td>{['card', 'eft', 'cash_payment', 'cash'].includes(t.kind) ? `${rand(t.amount_cents)} (${t.kind === 'cash_payment' ? 'cash' : t.kind})` : ''}</td><td>{rand(t.balance_cents)}</td><td><button disabled={busy} onClick={() => act(() => download('/transactions/' + t.id + '/receipt', t.receipt_name))}>View</button></td></tr>)}</tbody></table></div>
      </> : <p>No card transactions for this month yet.</p>}
      {submitted.length > 0 && <form className="form-card" onSubmit={e => {
        e.preventDefault();
        act(async () => {
          const form = new FormData();
          form.append('payload', JSON.stringify(payment));
          form.append('receipt', receipt);
          await apiForm(url('/transactions'), form);
          setMid('');
          setPayment(emptyPayment());
          setReceipt(null);
          e.target.reset();
        }, 'Payment and receipt saved.');
      }}><h2>Add payment and receipt</h2><fieldset disabled={busy}><div className="req-form-grid">
        <label>Requisition<select required value={payment.requisition_id} onChange={e => setPayment({
                ...payment,
                requisition_id: e.target.value
              })}><option value="">Choose requisition</option>{submitted.map(r => <option key={r.id} value={r.id}>{r.number} · {r.reference} · {r.deceased}</option>)}</select></label>
        <label>Receipt date<input required type="date" value={payment.transaction_date} onChange={e => setPayment({
                ...payment,
                transaction_date: e.target.value
              })} /></label>
        <label>Payment method<select value={payment.kind} onChange={e => setPayment({
                ...payment,
                kind: e.target.value
              })}><option value="card">Card</option><option value="eft">EFT</option><option value="cash">Cash</option></select></label>
        <label>Supplier<input required maxLength={255} value={payment.supplier} onChange={e => setPayment({
                ...payment,
                supplier: e.target.value
              })} /></label>
        <label>Purchase / service<input required maxLength={1000} value={payment.description} onChange={e => setPayment({
                ...payment,
                description: e.target.value
              })} /></label>
        <label>Amount paid (R)<input required type="number" min="0.01" max="10000000" step="0.01" value={payment.amount} onChange={e => setPayment({
                ...payment,
                amount: e.target.value
              })} /></label>
        <label>Receipt / slip<input required type="file" accept="application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg" onChange={e => setReceipt(e.target.files[0] || null)} /></label>
      </div><button disabled={!receipt} type="submit">Save payment</button></fieldset></form>}
    </>}
    {view === 'settings' && access.can_manage && <><form className="form-card" onSubmit={e => {
        e.preventDefault();
        act(() => apiRequest(url('/report-settings'), {
          method: 'PUT',
          body: JSON.stringify({
            recipient
          })
        }), 'Monthly report email saved.');
      }}><h2>Monthly card report</h2><p>Sent on the 30th at 17:00 South African time. In February, sent on the last day.</p><label>Email address<input required type="email" value={recipient} onChange={e => setRecipient(e.target.value)} /></label><p><button disabled={busy}>Save email</button></p></form><section className="form-card"><h2>Staff with requisition access</h2>{staff.map(person => <label className="req-simple-check" key={person.id}><input type="checkbox" checked={person.enabled} disabled={busy} onChange={e => act(() => apiRequest(url('/grants'), {
            method: 'PUT',
            body: JSON.stringify({
              user_id: person.id,
              enabled: e.target.checked
            })
          }))} />{person.full_name}</label>)}</section></>}
  </section>;
}
