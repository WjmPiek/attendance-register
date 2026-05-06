import React, { useRef, useState } from 'react'

export default function DragDropFileInput({
  label = 'Upload file',
  accept,
  file,
  onFile,
  required = false,
  help = 'Drag and drop a file here, or click to browse.',
  preview = false,
}) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const selectFile = (nextFile) => {
    if (!nextFile) {
      onFile?.(null)
      return
    }
    if (accept) {
      const accepted = accept.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean)
      const name = nextFile.name.toLowerCase()
      const type = (nextFile.type || '').toLowerCase()
      const ok = accepted.some((rule) => {
        if (rule.endsWith('/*')) return type.startsWith(rule.replace('/*', '/'))
        if (rule.startsWith('.')) return name.endsWith(rule)
        return type === rule
      })
      if (!ok) {
        window.alert('This file type is not allowed for this upload.')
        return
      }
    }
    onFile?.(nextFile)
  }

  const onDrop = (event) => {
    event.preventDefault()
    event.stopPropagation()
    setDragging(false)
    selectFile(event.dataTransfer.files?.[0] || null)
  }

  return (
    <div className="drag-upload-field">
      <label className="drag-upload-label">{label}{required ? <span className="required-dot"> *</span> : null}</label>
      <button
        type="button"
        className={`drag-upload-box ${dragging ? 'dragging' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(e) => { e.preventDefault(); setDragging(true) }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={(e) => { e.preventDefault(); setDragging(false) }}
        onDrop={onDrop}
      >
        <span className="drag-upload-icon">+</span>
        <strong>{file ? file.name : 'Drop file here'}</strong>
        <small>{file ? `${Math.round(file.size / 1024)} KB selected` : help}</small>
        {preview && file && file.type?.startsWith('image/') ? (
          <img className="drag-upload-preview" alt="Selected preview" src={URL.createObjectURL(file)} />
        ) : null}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        required={required && !file}
        onChange={(e) => selectFile(e.target.files?.[0] || null)}
        className="hidden-file-input"
      />
    </div>
  )
}
