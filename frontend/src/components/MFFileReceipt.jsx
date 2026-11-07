import CommissionEvidenceImport from './CommissionEvidenceImport'

export default function MFFileReceipt({ franchiseId }) {
  return <CommissionEvidenceImport kind="receipt" franchiseId={franchiseId}/>
}
