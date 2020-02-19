// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.provide("erpnext.hr");
// this.frm.add_fetch('company', 'nationality', 'target_nationality');
erpnext.hr.EmployeeController = frappe.ui.form.Controller.extend({
    setup: function () {
        this.frm.fields_dict.user_id.get_query = function (doc, cdt, cdn) {
            return {
                query: "frappe.core.doctype.user.user.user_query",
                filters: {ignore_user_type: 1}
            }
        }
        this.frm.fields_dict.reports_to.get_query = function (doc, cdt, cdn) {
            return {query: "erpnext.controllers.queries.employee_query"}
        }

        this.frm.fields_dict.designation.get_query = function () {
            return {
                filters: {
                    'department': cur_frm.doc.department
                }
            }
        }
    },
    department: function () {
        if (cur_frm.doc.department == '' || cur_frm.doc.department == 'undefined') {
            cur_frm.set_value('designation', '');
            cur_frm.set_value('position', '');
        }
    },
    refresh: function () {

        check_row_number(cur_frm)// Validate Projects rows

        var me = this;
        erpnext.toggle_naming_series();


        cur_frm.set_query("position", function () {
            return {
                query: "erpnext.hr.doctype.employee.employee.get_unused_position",
                "filters": [
                    ['designation', '=', cur_frm.doc.designation],
                    ['department', '=', cur_frm.doc.department]
                ]
            };
        });

    },
    date_of_birth: function () {
        var age = frappe.datetime.get_diff(frappe.datetime.nowdate(), this.frm.doc.date_of_birth)

        // var min_age = frappe.db.get_single_value("HR Settings", "retirement_age_for_male")
        frappe.call({
            "method": "erpnext.hr.doctype.employee.employee.check_employee_min_age",
            callback: function (r) {
                if (r.message) {
                    if (cint(age / 365.25) < cint(r.message)) {
                        cur_frm.get_field('date_of_birth').set_description(__('<font color=red>Employee age Must Be over ' + r.message + '</font>'))
                    } else {
                        cur_frm.get_field('date_of_birth').set_description('');
                    }

                }
            }
        });


        return cur_frm.call({
            method: "erpnext.hr.doctype.employee.employee.get_retirement_date_for_gender",
            args: {date_of_birth: this.frm.doc.date_of_birth, gender: this.frm.doc.gender}
        });
    },
    employee_id: function () {
        var val = cur_frm.doc.employee_id;
        if (isNaN(val)) {
            cur_frm.get_field('employee_id').set_description(__('<font color=red>this is not a number...please enter numbers only </font>'))
        } else if (val.length > 7) {
            cur_frm.get_field('employee_id').set_description(__('<font color=red>Employee ID Must Be Seven Numbers Or Less </font>'))
        } else {
            frappe.db.get_value('Employee', {'name': val}, 'name', (r) => {
                if (r && r.name) {
                    cur_frm.get_field('employee_id').set_description(__('<font color=red>Employee ID Is Already Exist.. </font>'))
                }
            });
        }

    },
    id_number: function () {
        var val = cur_frm.doc.id_number;
        if (isNaN(val)) {
            cur_frm.get_field('id_number').set_description(__('<font color=red>this is not a number...please enter numbers only </font>'))
        } else if (val.length != 10) {
            cur_frm.get_field('id_number').set_description(__('<font color=red>Employee ID Must Be Ten Numbers </font>'))
        } else {
            frappe.db.get_value('Employee', {'id_number': val}, 'id_number', (r) => {
                if (r && r.id_number) {
                    cur_frm.get_field('id_number').set_description(__('<font color=red>ID Number is Already Exist.. </font>'))
                }
            });
        }
    },
    employment_type: function () {
        this.frm.toggle_reqd("contract_end_date", this.frm.doc.employment_type == "Intern" ? 1 : 0);

        if (this.frm.doc.employment_type) {
            return cur_frm.call({
                method: "get_test_period_end_date",
                async: false,
                args: {date_of_joining: cur_frm.doc.date_of_joining},
                /* callback: function(r) {
                    cur_frm.toggle_reqd("test_period_end_date", cur_frm.doc.employment_type == "Under Test" ? 1 : 0);
                  }*/
            });
        }
        //cur_frm.toggle_reqd("test_period_end_date", cur_frm.doc.employment_type == "Under Test" ? 1 : 0);
    },

    date_of_joining: function () {
        if (this.frm.doc.employment_type) {
            return cur_frm.call({
                method: "get_test_period_end_date",
                async: false,
                args: {date_of_joining: cur_frm.doc.date_of_joining}
            });
        }
    },

    citizen_or_resident: function () {
        this.frm.toggle_reqd("nationality", this.frm.doc.citizen_or_resident == "Resident" ? 1 : 0);
        this.frm.toggle_reqd("id_number", this.frm.doc.citizen_or_resident == "Citizen" ? 1 : 0);

        if (this.frm.doc.citizen_or_resident == "Citizen") {
            this.frm.set_value("nationality", this.frm.doc.target_nationality);
        }

    },

    finger_print_number: function () {
        cur_frm.fp_changed = true;
    },
    resignation_letter_date: function () {
        this.frm.toggle_reqd("reason_for_resignation", this.frm.doc.resignation_letter_date ? 1 : 0);

    },
    gender: function () {
        return cur_frm.call({
            method: "erpnext.hr.doctype.employee.employee.get_retirement_date_for_gender",
            args: {date_of_birth: this.frm.doc.date_of_birth, gender: this.frm.doc.gender}
        });
    },

    salutation: function () {
        if (this.frm.doc.salutation) {
            this.frm.set_value("gender", {
                "Mr": "Male",
                "Ms": "Female"
            }[this.frm.doc.salutation]);
        }
    },

});
frappe.ui.form.on('Employee', {
    setup: function (frm) {
        frm.set_query("leave_policy", function () {
            return {
                "filters": {
                    "docstatus": 1
                }
            };
        });
    },
    onload: function (frm) {
        frm.set_query("department", function () {
            return {
                "filters": {
                    "company": frm.doc.company,
                }
            };
        });
    },
    prefered_contact_email: function (frm) {
        frm.events.update_contact(frm)
    },
    personal_email: function (frm) {
        frm.events.update_contact(frm)
    },
    company_email: function (frm) {
        frm.events.update_contact(frm)
    },
    user_id: function (frm) {
        frm.events.update_contact(frm)
    },
    update_contact: function (frm) {
        var prefered_email_fieldname = frappe.model.scrub(frm.doc.prefered_contact_email) || 'user_id';
        frm.set_value("prefered_email",
            frm.fields_dict[prefered_email_fieldname].value)
    },
    status: function (frm) {
        return frm.call({
            method: "deactivate_sales_person",
            args: {
                employee: frm.doc.employee,
                status: frm.doc.status
            }
        });
    },
    create_user: function (frm) {
        if (!frm.doc.prefered_email) {
            frappe.throw(__("Please enter Preferred Contact Email"))
        }
        frappe.call({
            method: "erpnext.hr.doctype.employee.employee.create_user",
            args: {employee: frm.doc.name, email: frm.doc.prefered_email},
            callback: function (r) {
                frm.set_value("user_id", r.message)
            }
        });
    },
    create_position: function (frm) {

        if (!frm.doc.designation) {
            frappe.throw(__("Please enter Designation"))
        }

        if (!frm.doc.department) {
            frappe.throw(__("Please enter Department"))
        }

        frappe.call({
            method: "erpnext.hr.doctype.employee.employee.create_position",
            args: {designation: frm.doc.designation, department: frm.doc.department},
            callback: function (r) {
                frm.set_value("position", r.message)
            }
        });
    }


});

cur_frm.cscript = new erpnext.hr.EmployeeController({frm: cur_frm});


frappe.ui.form.on('Employee', 'validate', function (frm) {
    if (frm.doc.finger_print_number && cur_frm.fp_changed) {
        return new Promise(function (resolve, reject) {
            frappe.confirm(
                'Finger Print Number has changed \n' +
                'Make sure to get latest fingerprint log for Emp \n' +
                'Do you want to proceed ?',
                function () {
                    var negative = 'frappe.validated = false';
                    resolve(negative);
                    cur_frm.fp_changed = false;
                },
                function () {
                    reject();
                }
            )
        })
    }
});

frappe.ui.form.on('Projects', {
    refresh:function(frm, dt, dn){
        check_row_number(frm, dt, dn)
    },
    projects_add: function (frm, dt, dn) {
		check_row_number(frm, dt, dn)
    },
    before_projects_remove:function(frm, dt, dn){
        check_row_reference(frm,dt,dn)
    },
    projects_remove: function (frm, dt, dn) {
		check_row_number(frm, dt, dn)
    }
});

let check_row_reference = function(frm,dt,dn){
     var tbl = frm.doc.projects || [];

    frappe.call({
        method:"Check_project_reference",
        doc:frm.doc,
        args:{row_name:dn},
        callback:function (r) {
            if(r.message){
                frappe.throw(__("row cannot be deleted...because it is linked with other row"))
            }
        }
    });
}

let check_row_number = function (frm, dt, dn) {
    var tbl = frm.doc.projects || [];
    if (tbl.length >= 1) {
        cur_frm.fields_dict['projects'].grid.wrapper.find('.grid-add-row').hide();
    } else {
        cur_frm.fields_dict['projects'].grid.wrapper.find('.grid-add-row').show();
    }
}