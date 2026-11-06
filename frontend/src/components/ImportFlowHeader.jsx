import {useEffect} from 'react'
import {scrollImportTop} from './ImportFeedback'

export default function ImportFlowHeader({title,page,onBack,busy}) {
  useEffect(()=>{scrollImportTop()},[page])
  const titles={select:'Choose documents',review:'Review extracted details',confirm:'Review fees and save',matched:'Matched commission results',complete:'Documents saved',history:'Saved documents'}
  return <header className="form-card import-flow-header">
    {page!=='select'&&<button type="button" className="glass-button" disabled={busy} onClick={onBack}>← Back</button>}
    <p className="muted">{title}</p><h2>{titles[page]}</h2>
  </header>
}
