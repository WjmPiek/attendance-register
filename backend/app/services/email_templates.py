def branded_email(
    franchise_name: str,
    metrics: dict,
    leave_rows: list,
    button_text: str = None,
    button_url: str = None
) -> str:

    button = ""
    if button_text and button_url:
        button = f"""
        <p>
          <a href="{button_url}" style="
            background:#8f5cc2;
            color:white;
            padding:12px 18px;
            border-radius:12px;
            text-decoration:none;
            font-weight:bold;
          ">
            {button_text}
          </a>
        </p>
        """

    leave_html = "".join([
        f"""
        <tr>
            <td>{r['name']} {r['surname']}</td>
            <td>{r['leave_type']}</td>
            <td>{r['start_date']} → {r['end_date']}</td>
            <td>{r['days_requested']}</td>
            <td>{str(r['status']).title()}</td>
        </tr>
        """
        for r in leave_rows
    ])

    return f"""
    <div style="font-family:Arial;background:#f4f6fb;padding:20px;">

      <div style="max-width:720px;margin:auto;background:white;border-radius:16px;padding:20px;">

        <h2 style="color:#4f46e5;margin-bottom:10px;">
          {franchise_name} - Daily Summary
        </h2>

        <div style="display:flex;gap:12px;margin:20px 0;flex-wrap:wrap;">
          
          <div style="flex:1;background:#eef2ff;padding:12px;border-radius:12px;">
            <strong>Total Staff</strong><br>
            <span style="font-size:22px;">{metrics.get('total_staff', 0)}</span>
          </div>

        </div>

        <div style="display:flex;gap:10px;margin-top:10px;flex-wrap:wrap;">

          <div style="background:#fee2e2;padding:10px;border-radius:10px;">
            ❌ Not Signed In<br><strong>{metrics.get('not_signed_in', 0)}</strong>
          </div>

          <div style="background:#fef3c7;padding:10px;border-radius:10px;">
            ⏰ Late<br><strong>{metrics.get('late', 0)}</strong>
          </div>

          <div style="background:#e0f2fe;padding:10px;border-radius:10px;">
            ⚠ Missing Sign-out<br><strong>{metrics.get('missing_sign_out', 0)}</strong>
          </div>

        </div>

        <h3 style="margin-top:20px;">📅 Leave Planner</h3>

        <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:10px;">
          <thead>
            <tr style="background:#f3f4f6;">
              <th align="left">Employee</th>
              <th align="left">Type</th>
              <th align="left">Dates</th>
              <th align="left">Days</th>
              <th align="left">Status</th>
            </tr>
          </thead>
          <tbody>
            {leave_html or '<tr><td colspan="5">No leave records</td></tr>'}
          </tbody>
        </table>

        {button}

        <hr style="margin:20px 0;">

        <p style="font-size:12px;color:#888;">
          Attendance Register Platform • Automated Report
        </p>

      </div>
    </div>
    """