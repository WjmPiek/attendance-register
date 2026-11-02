import { useEffect, useState } from 'react'
import { apiRequest, apiBlob } from '../api/client'
import MonthlyCommissionStatement from './MonthlyCommissionStatement'

const currentMonth = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }
export default function BranchCommissionHub({ franchiseId, onOpenEmployee }) {
  const [data, setData] = useState(null), [error, setError] = useState('')
  const [month, setMonth] = useState(currentMonth), [selected, setSelected] = useState(null)
  const suffix = franchiseId ? `?franchise_user_id=${franchiseId}` : ''
  useEffect(() => { let active = true; apiRequest(`/receipt-commissions/settings${suffix}`).then(d => { if (active) setData(d) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [suffix])
  const download = async (branch, employee) => {
    try {
      const query = new URLSearchParams({ month, ...(franchiseId ? { franchise_user_id: franchiseId } : {}), ...(branch ? { branch_id: branch } : {}), ...(employee ? { employee_user_id: employee } : {}) })
      const blob = await apiBlob(`/receipt-commissions/report.pdf?${query}`)
      const link = document.createElement('a'); const url = URL.createObjectURL(blob); link.href = url; link.download = `commissions-${month}.pdf`; link.click(); URL.revokeObjectURL(url)
    } catch (e) { setError(e.message) }
  }
  return <section className="mortuary-book"><div className="form-card"><h2>All branches · Employees and commissions</h2><p>Staff remain under their home branch. Commission imports can find active staff across this holder’s linked branches.</p><label>Report month<input type="month" value={month} onChange={e => setMonth(e.target.value)}/></label><button type="button" className="glass-button" onClick={() => download()}>Download all branches PDF</button>{error && <p role="alert" className="error-message">{error}</p>}</div>
    {data?.branches.map(branch => <section className="form-card" key={branch.id}><div className="section-heading"><h3>{branch.name}</h3><button type="button" onClick={() => download(branch.id)}>Download branch commissions PDF</button></div>{data.employees.filter(e => e.branch_id === branch.id).map(e => <div className="mortuary-allocation" key={e.user_id}><strong>{e.full_name}<small> · {e.employee_role}</small></strong><button type="button" className="glass-button" onClick={() => setSelected(e)}>Monthly commissions</button><button type="button" className="glass-button" onClick={() => download(branch.id, e.user_id)}>Employee PDF</button></div>)}{!data.employees.some(e => e.branch_id === branch.id) && <p>No active employees assigned to this branch.</p>}</section>)}
    {selected && <section className="form-card"><button type="button" className="glass-button" onClick={() => setSelected(null)}>Close employee statement</button><h3>{selected.full_name} · {selected.branch_name}</h3><MonthlyCommissionStatement employeeUserId={selected.user_id} franchiseId={franchiseId}/></section>}
  </section>
}
