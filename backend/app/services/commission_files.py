"""Private original evidence and upload audit records for all three document types."""
from sqlalchemy import text
from app.services.audit import write_audit_log


def store_file(db, fid, digest, filename, content, actor, kind, accepted_pages):
    db.execute(text('''INSERT INTO commission_document_files(franchise_user_id,source_hash,filename,file_content,uploaded_by_user_id)
        VALUES(:fid,:hash,:name,:content,:actor) ON CONFLICT(franchise_user_id,source_hash) DO NOTHING'''),
        {'fid':fid,'hash':digest,'name':filename,'content':content,'actor':actor})
    write_audit_log(db, actor_user_id=actor, franchise_user_id=fid, action='commission_file_uploaded',
                    entity_type='commission_documents', entity_id=digest,
                    new_values={'filename':filename,'kind':kind,'accepted_pages':accepted_pages})
