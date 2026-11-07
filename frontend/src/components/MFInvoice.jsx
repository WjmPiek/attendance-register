import CommissionEvidenceImport from './CommissionEvidenceImport'

export default function MFInvoice({ franchiseId }) {
  return <CommissionEvidenceImport kind="invoice" franchiseId={franchiseId}/>
}
