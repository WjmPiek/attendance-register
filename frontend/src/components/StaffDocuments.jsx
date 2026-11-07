import { useEffect, useRef, useState } from 'react'
import { getMyPayslips, getMyIrp5Documents, downloadPayslip, downloadIrp5Document } from '../api/client'

export default function StaffDocuments({ kind }) {
  const [docs,setDocs]=useState(null),[error,setError]=useState(''),[selected,setSelected]=useState(null)
  const [password,setPassword]=useState(''),[busy,setBusy]=useState(false),[preview,setPreview]=useState(null)
  const passwordRef=useRef(null)
  useEffect(()=>{let active=true;setDocs(null);setError('');(kind==='payslips'?getMyPayslips():getMyIrp5Documents()).then(items=>{if(active)setDocs(items)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[kind])
  useEffect(()=>{if(selected)passwordRef.current?.focus()},[selected])
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url)},[preview])
  const open=async event=>{
    event.preventDefault();setBusy(true);setError('')
    try {
      const blob=await (kind==='payslips'?downloadPayslip:downloadIrp5Document)(selected.id,password)
      setPreview({url:URL.createObjectURL(blob),image:blob.type.startsWith('image/'),name:selected.original_filename || 'Document.pdf'})
      setPassword('');setSelected(null)
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  if(preview)return <section className="staff-document-view"><button type="button" onClick={()=>setPreview(null)}>Back to documents</button><a href={preview.url} download={preview.name}>Download</a>{preview.image?<img src={preview.url} alt={preview.name}/>:<iframe src={preview.url} title={preview.name}/>}</section>
  return <section>
    {error&&<p className="error-message" role="alert">{error}</p>}
    {!docs&&!error&&<p role="status">Loading…</p>}
    <div className="staff-document-list">{docs?.map(doc=><button type="button" key={doc.id} onClick={()=>{setSelected(doc);setPassword('');setError('')}}><span>{doc.original_filename || (kind==='payslips'?'Payslip':'IRP5')}{doc.tax_year?` · ${doc.tax_year}`:''}</span><span>Open →</span></button>)}</div>
    {docs?.length===0&&<p>No documents available.</p>}
    {selected&&<form className="staff-simple-form" onSubmit={open}><label>Password<input ref={passwordRef} type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required disabled={busy}/></label><button disabled={busy}>Open document</button><button type="button" disabled={busy} onClick={()=>{setSelected(null);setPassword('')}}>Cancel</button></form>}
  </section>
}
