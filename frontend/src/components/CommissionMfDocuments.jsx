import {useEffect,useRef,useState} from 'react'
import {apiRequest,apiBlob} from '../api/client'

const kinds=[['mortuary','Mortuary Book'],['invoice','MF Invoice'],['receipt','MF File Receipts']]
const fields={reference:'MF file',deceased:'Deceased',id_number:'ID number',service_date:'Service date',invoice_number:'Invoice number',receipt_number:'Receipt number',invoice_total:'Invoice total',gross_received:'Amount received'}

export default function CommissionMfDocuments({branchId,reference,personId,category,franchiseId}) {
  const [result,setData]=useState(null),[error,setError]=useState(''),[pdf,setPdf]=useState(null),[busy,setBusy]=useState(false)
  const query=new URLSearchParams({earning_branch_id:branchId,reference,employee_user_id:personId,commission_type:category,...(franchiseId?{franchise_user_id:franchiseId}:{})}).toString()
  const currentQuery=useRef(query)
  const data=result?.scope===query?result:null
  useEffect(()=>{
    let active=true
    currentQuery.current=query;setData(null);setError('');setPdf(null);setBusy(false)
    if(!Number.isInteger(Number(branchId))||Number(branchId)<=0){setError('This older claim has no earning branch. Head Office must review its branch details.');return}
    apiRequest(`/commission/case-documents?${query}`).then(result=>{if(active)setData({...result,scope:query})}).catch(failure=>{if(active)setError(failure.message)})
    return()=>{active=false;currentQuery.current=''}
  },[query])
  useEffect(()=>()=>{if(pdf)URL.revokeObjectURL(pdf.url)},[pdf])
  const open=async(doc,download=false)=>{
    const requestQuery=query
    setBusy(true);setError('');setPdf(null)
    try {
      const blob=await apiBlob(`/commission/case-documents/${doc.id}/file?${query}`)
      const url=URL.createObjectURL(blob)
      if(currentQuery.current!==requestQuery){URL.revokeObjectURL(url);return}
      const title=`${kinds.find(([kind])=>kind===doc.kind)?.[1] || 'Document'} ${doc.record.receipt_number || doc.record.invoice_number || reference}`
      if(download){const link=document.createElement('a');link.href=url;link.download=`${doc.kind}-MF${reference}.pdf`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
      else setPdf({url,title,query})
    }catch(failure){if(currentQuery.current===requestQuery)setError(failure.message)}
    finally{if(currentQuery.current===requestQuery)setBusy(false)}
  }
  return <section className="commission-mf-documents">
    <h3>Imported documents</h3>
    {error&&<p role="alert" className="error-message">{error}</p>}
    {!data&&!error&&<p role="status">Loading MF file documents…</p>}
    {data&&<>
      <p className={data.case.ready?'success-message':'muted'}>{data.case.ready?'Documents complete':'Waiting for document checks'} · {data.case.reason}</p>
      <p className="muted">Documents for this branch and MF file, across all upload months.</p>
      {kinds.map(([kind,label])=>{const documents=data.documents.filter(doc=>doc.kind===kind);return <section className="mortuary-record" key={kind}>
        <h4>{label}</h4>
        {!documents.length&&<p>Not imported yet.</p>}
        {documents.map(doc=><article className="commission-mf-document" key={doc.id}>
          <p>{label} {doc.record.receipt_number || doc.record.invoice_number || doc.record.reference}</p>
          {doc.record.service_date&&<p>{doc.record.service_date}</p>}
          {doc.original_available?<div className="button-row"><button type="button" disabled={busy} onClick={()=>open(doc)}>View PDF</button><button type="button" className="glass-button" disabled={busy} onClick={()=>open(doc,true)}>Download PDF</button></div>:<p>The original PDF was not retained for this older import. Its saved details are available below.</p>}
          <details><summary>View imported details</summary><dl className="document-field-list">{Object.entries(fields).filter(([key])=>doc.record[key]!=null&&doc.record[key]!=='').map(([key,title])=><div key={key}><dt>{title}</dt><dd>{String(doc.record[key])}</dd></div>)}</dl></details>
        </article>)}
      </section>})}
    </>}
    {pdf&&pdf.query===query&&<section><div className="button-row"><h4>{pdf.title}</h4><button type="button" className="glass-button" onClick={()=>setPdf(null)}>Close PDF</button></div><iframe className="commission-document-pdf" src={pdf.url} title={pdf.title}/></section>}
  </section>
}
