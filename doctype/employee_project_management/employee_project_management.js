// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee Project Management', {
	// refresh: function(frm) {

	// }
    employee:function (frm) {
        if(frm.doc.employee) {
            frappe.call({
                method: "get_employee_project",
                doc: frm.doc,
                args: {employee: frm.doc.employee},
                callback: function (r) {
                    if (r.message) {
                        frm.set_value('current_project',r.message.project);
                        frm.set_value('start_date',r.message.start_date);
                        frm.set_value('end_date',r.message.end_date);
                    }
                    else {
                        frm.set_value('current_project','');
                        frm.set_value('start_date','');
                        frm.set_value('end_date','');
                    }
                }
            });
        }
        else{
                frm.set_value('employee_name','');
                frm.set_value('employee_department','');
                frm.set_value('current_project','');
                frm.set_value('start_date','');
                frm.set_value('end_date','');
        }
    }
});
