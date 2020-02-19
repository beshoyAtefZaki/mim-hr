// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Sponsor', {
	refresh: function(frm) {

	}
});
frappe.ui.form.on('Sponsor','validate',function(frm){
	if (frm.doc.telephone) {
	if(! validatePhone(frm.doc.telephone))
		{
			frappe.msgprint(__("Sorry.. it is not a valid telephone"));
			cur_frm.set_value("telephone","");
			frappe.validated = false;
		}

    }
    if (frm.doc.mobile) {
		if(! validatePhone(frm.doc.mobile))
		{
			frappe.msgprint(__("Sorry.. it is not a valid mobile"));
			cur_frm.set_value("mobile","");
			frappe.validated = false;
		}
	}


}
);

function validatePhone(txtPhone) {
	var filter = /^[0-9-+]+$/;
		if (filter.test(txtPhone)) {
			return true;
		}
		else {
			return false;
		}
}