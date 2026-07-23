<label>EMPL. NO</label>
<input
  value={employee.employee_number || ''}
  onChange={(e) => updateEmployee('employee_number', e.target.value)}
/>
