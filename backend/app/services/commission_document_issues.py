"""Actions for the evidence check that currently blocks an MF folder."""


def document_issues(documents, ready, reason):
    if ready:
        return []
    labels = {'mortuary': 'Mortuary Book', 'invoice': 'MF Invoice', 'receipt': 'MF File Receipt'}
    missing = [kind for kind in labels if not any(d['kind'] == kind for d in documents)]
    if missing:
        return [{'action': 'upload', 'kind': kind, 'label': 'Upload ' + labels[kind],
                 'message': labels[kind] + ' is missing for this branch and MF File.', 'document_ids': []}
                for kind in missing]
    lower = str(reason).lower()
    if 'vat' in lower:
        return [{'action': 'main_vat', 'label': 'Check branch VAT in the main system', 'message': reason,
                 'document_ids': [d['id'] for d in documents if d['kind'] == 'invoice']}]
    kinds = ('receipt', 'invoice') if any(word in lower for word in ('paid', 'receipts exceed', 'receipt invoice', 'receipt number', 'payment receipt', 'linked receipt')) else tuple(labels)
    if 'branch is no longer' in lower:
        return [{'action': 'branch', 'label': 'Check branch access in the main system', 'message': reason, 'document_ids': []}]
    return [{'action': 'inspect', 'label': 'Check the documents below', 'message': reason,
             'document_ids': [d['id'] for d in documents if d['kind'] in kinds]}]
