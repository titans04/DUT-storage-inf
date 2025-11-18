@admin_bp.route('/items/export/<string:format>', methods=['GET'])
@login_required
@admin_required
def export_items(format):
    """Export filtered inventory (EXACT same filters as view_inventory)"""
    from datetime import datetime
    from sqlalchemy import and_, or_
    from io import BytesIO
    import pandas as pd

    # === REUSE EXACT SAME QUERY LOGIC AS view_inventory ===
    query = db.select(Item) \
        .join(Room, Item.room_id == Room.room_id) \
        .join(Campus, Room.campus_id == Campus.campus_id) \
        .outerjoin(DataCapturer, Item.data_capturer_id == DataCapturer.data_capturer_id)

    # Admin scope (same as view_inventory)
    if not current_user.is_super_admin:
        allowed_campuses = [c.campus_id for c in current_user.campuses]
        query = query.where(Room.campus_id.in_(allowed_campuses))

    # === ALL FILTERS FROM view_inventory (exact match) ===
    if campus_id := request.args.get("campus_id"):
        if campus_id.isdigit() and (current_user.is_super_admin or int(campus_id) in [c.campus_id for c in current_user.campuses]):
            query = query.where(Room.campus_id == int(campus_id))

    if room_id := request.args.get("room_id"):
        if room_id.isdigit():
            query = query.where(Item.room_id == int(room_id))

    if status := request.args.get("status"):
        if status != "all":
            try:
                query = query.where(Item.status == ItemStatus[status.upper()])
            except KeyError:
                flash("Invalid status.", "warning")

    if category := request.args.get("category"):
        if category != "all":
            try:
                query = query.where(Item.category == ItemCategory[category.upper()])
            except KeyError:
                flash("Invalid category.", "warning")

    # Responsible Staff (name or staff number)
    if staff := request.args.get("staff"):
        query = query.where(
            or_(
                Room.staff_name.ilike(f"%{staff}%"),
                Room.staff_number.ilike(f"%{staff}%")
            )
        )

    # Data Capturer
    if capturer := request.args.get("capturer"):
        subq = db.select(DataCapturer.data_capturer_id).where(
            or_(
                DataCapturer.full_name.ilike(f"%{capturer}%"),
                DataCapturer.student_number.ilike(f"%{capturer}%")
            )
        )
        capturer_ids = db.session.execute(subq).scalars().all()
        if capturer_ids:
            query = query.where(Item.data_capturer_id.in_(capturer_ids))

    # Cost range
    cost_filters = []
    if min_cost := request.args.get("min_cost"):
        try:
            cost_filters.append(Item.cost >= float(min_cost))
        except:
            pass
    if max_cost := request.args.get("max_cost"):
        try:
            cost_filters.append(Item.cost <= float(max_cost))
        except:
            pass
    if cost_filters:
        query = query.where(and_(*cost_filters))

    # Date range
    date_filters = []
    if date_from := request.args.get("date_from"):
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d").date()
            date_filters.append(Item.Procured_date >= start)
        except:
            pass
    if date_to := request.args.get("date_to"):
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d").date()
            date_filters.append(Item.Procured_date <= end)
        except:
            pass
    if date_filters:
        query = query.where(and_(*date_filters))

    # Execute query
    items = db.session.execute(query).scalars().all()

    if not items:
        flash("No items match your filters to export.", "info")
        return redirect(url_for('admin.view_inventory'))

    # === Build DataFrame (same columns as your old one) ===
    data = []
    for i in items:
        data.append({
            "Asset No.": i.asset_number or "",
            "Serial No.": i.serial_number or "",
            "Name": i.name,
            "Brand": i.brand or "",
            "Color": i.color or "",
            "Capacity/Specs": i.capacity or "",
            "Category": i.category.value if i.category else "",
            "Cost (R)": float(i.cost) if i.cost else 0.00,
            "Status": i.status.value,
            "Captured By": i.data_capturer.full_name if i.data_capturer else "",
            "Room": i.room.name,
            "Campus": i.room.campus.name,
            "Room Staff": i.room.staff_name or "",
            "Staff ID": i.room.staff_number or "",
            "Procured Date": i.Procured_date.strftime("%Y-%m-%d") if i.Procured_date else "",
            "Captured Date": i.capture_date.strftime("%Y-%m-%d") if i.capture_date else "",
        })

    df = pd.DataFrame(data)
    df_summary = df.groupby(['Name', 'Status']).size().reset_index(name='Count')

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # === EXCEL EXPORT (Enhanced with proper column widths) ===
    if format == "xlsx":
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            workbook = writer.book
            
            # Professional formatting
            header_format = workbook.add_format({
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'font_size': 11
            })
            
            cell_format = workbook.add_format({
                'border': 1,
                'valign': 'vcenter',
                'text_wrap': True
            })
            
            money_fmt = workbook.add_format({
                'num_format': 'R#,##0.00',
                'border': 1,
                'valign': 'vcenter'
            })
            
            date_fmt = workbook.add_format({
                'num_format': 'yyyy-mm-dd',
                'border': 1,
                'valign': 'vcenter'
            })

            # === SUMMARY SHEET ===
            # Write to Excel WITHOUT headers first
            df_summary.to_excel(writer, sheet_name="Summary", index=False, header=False, startrow=1)
            sheet = writer.sheets["Summary"]
            
            # Now manually write headers in row 0
            sheet.set_row(0, 20)
            for col, val in enumerate(df_summary.columns):
                sheet.write(0, col, val, header_format)
            
            # Auto-adjust column widths for summary
            for idx, col in enumerate(df_summary.columns):
                max_len = max(
                    df_summary[col].astype(str).apply(len).max(),
                    len(str(col))
                ) + 2
                sheet.set_column(idx, idx, min(max_len, 50))
            
            # Apply cell formatting to summary data rows
            for row in range(1, len(df_summary) + 1):
                for col in range(len(df_summary.columns)):
                    sheet.write(row, col, df_summary.iloc[row-1, col], cell_format)
            
            # Set row height for header
            sheet.set_row(0, 30)

            # === INVENTORY SHEET ===
            # Write to Excel WITHOUT headers first
            df.to_excel(writer, sheet_name="Inventory", index=False, header=False, startrow=1)
            sheet = writer.sheets["Inventory"]
            
            # Now manually write headers in row 0
            sheet.set_row(0, 20)
            for col, val in enumerate(df.columns):
                sheet.write(0, col, val, header_format)
            
            # Define optimal column widths for each column
            column_widths = {
                "Asset No.": 18,
                "Serial No.": 25,
                "Name": 25,
                "Brand": 15,
                "Color": 12,
                "Capacity/Specs": 20,
                "Category": 20,
                "Cost (R)": 12,
                "Status": 12,
                "Captured By": 20,
                "Room": 15,
                "Campus": 15,
                "Room Staff": 20,
                "Staff ID": 12,
                "Procured Date": 16,
                "Captured Date": 16
            }
            
            # Apply column widths and formatting - FIXED VERSION
            for idx, col in enumerate(df.columns):
                # Set column width
                width = column_widths.get(col, 15)
                sheet.set_column(idx, idx, width)
                
                # Apply cell formatting to data rows
                if col == "Cost (R)":
                    for row in range(1, len(df) + 1):
                        sheet.write(row, idx, df.iloc[row-1, idx], money_fmt)
                elif "Date" in col:
                    for row in range(1, len(df) + 1):
                        date_val = df.iloc[row-1, idx]
                        # Convert string date to datetime object for Excel
                        if date_val and isinstance(date_val, str):
                            try:
                                date_obj = datetime.strptime(date_val, "%Y-%m-%d")
                                sheet.write(row, idx, date_obj, date_fmt)
                            except:
                                sheet.write(row, idx, date_val, cell_format)
                        else:
                            sheet.write(row, idx, date_val if date_val else '', cell_format)
                else:
                    for row in range(1, len(df) + 1):
                        sheet.write(row, idx, df.iloc[row-1, idx], cell_format)
            
            # Set header row height
            sheet.set_row(0, 30)
            
            # Freeze top row for easy scrolling
            sheet.freeze_panes(1, 0)

        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"DUT_Inventory_Filtered_{timestamp}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # === PDF EXPORT (Using Paragraph objects for proper spacing) ===
    elif format == "pdf":
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A3, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_CENTER

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=landscape(A3),
            topMargin=1*cm,
            bottomMargin=1*cm,
            leftMargin=1*cm,
            rightMargin=1*cm
        )
        
        styles = getSampleStyleSheet()
        
        # Custom styles for table cells
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=8,
            alignment=TA_CENTER,
            leading=10
        )
        
        header_cell_style = ParagraphStyle(
            'HeaderCellStyle',
            parent=styles['Normal'],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.white,
            leading=11,
            fontName='Helvetica-Bold'
        )
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor('#001F3F'),
            spaceAfter=12
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#001F3F'),
            spaceAfter=8,
            spaceBefore=12
        )
        
        elements = []

        # Title
        title = Paragraph("DUT Inventory Report - Filtered Results", title_style)
        subtitle = Paragraph(
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} | Total Items: {len(df)}", 
            styles["Normal"]
        )
        elements.extend([title, subtitle, Spacer(1, 0.5*cm)])

        # === SUMMARY TABLE ===
        elements.append(Paragraph("Summary by Item & Status", heading_style))
        
        # Convert summary to Paragraph objects
        summary_data_para = []
        summary_headers = [Paragraph(str(col), header_cell_style) for col in df_summary.columns]
        summary_data_para.append(summary_headers)
        
        for _, row in df_summary.iterrows():
            row_paras = [Paragraph(str(val), cell_style) for val in row]
            summary_data_para.append(row_paras)
        
        summary_tbl = Table(summary_data_para, colWidths=[8*cm, 8*cm, 8*cm])
        summary_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#001F3F')),
            ('GRID', (0, 0), (-1, -1), 1.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(summary_tbl)
        elements.append(PageBreak())

        # === DETAILED TABLE with Paragraph objects ===
        elements.append(Paragraph("Detailed Inventory", heading_style))
        
        # Convert all data to Paragraph objects for proper wrapping
        detail_data_para = []
        
        # Headers
        headers = [Paragraph(str(col), header_cell_style) for col in df.columns]
        detail_data_para.append(headers)
        
        # Data rows
        for _, row in df.iterrows():
            row_paras = [Paragraph(str(val) if val else '', cell_style) for val in row]
            detail_data_para.append(row_paras)
        
        # Column widths that match DataFrame column order - FIXED VERSION
        detail_col_widths = [
            2.8*cm,  # Asset No.
            3.2*cm,  # Serial No.
            2.5*cm,  # Name
            2.0*cm,  # Brand
            1.8*cm,  # Color
            2.5*cm,  # Capacity/Specs
            3.0*cm,  # Category
            2.0*cm,  # Cost (R)
            2.0*cm,  # Status
            2.8*cm,  # Captured By
            2.0*cm,  # Room
            2.2*cm,  # Campus
            2.8*cm,  # Room Staff
            2.0*cm,  # Staff ID
            2.2*cm,  # Procured Date
            2.2*cm,  # Captured Date
        ]
        
        detail_tbl = Table(detail_data_para, colWidths=detail_col_widths, repeatRows=1)
        detail_tbl.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#001F3F')),
            ('GRID', (0, 0), (-1, -1), 1.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 2.5, colors.HexColor('#001F3F')),
            
            # Row backgrounds
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
            
            # Alignment
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(detail_tbl)

        doc.build(elements)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"DUT_Inventory_Filtered_{timestamp}.pdf",
            mimetype="application/pdf"
        )

    # Invalid format
    flash("Invalid export format.", "danger")
    return redirect(url_for('admin.view_inventory'))
