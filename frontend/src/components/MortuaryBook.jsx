import CommissionEvidenceImport from './CommissionEvidenceImport'

export default function MortuaryBook({ franchiseId }) {
  return <CommissionEvidenceImport kind="mortuary" franchiseId={franchiseId}/>
}
