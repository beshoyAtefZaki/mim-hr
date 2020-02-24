// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Social insurance Payroll', {
	// refresh: function(frm) {

	// }


	onload:function(frm){
		frappe.call({

			doc: frm.doc,
			method:"get_employee" ,
			callback :function(r){
				console.log(r)
			}


		})
	}
});
