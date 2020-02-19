// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt


cur_frm.set_value('for_emp','');
frappe.ui.form.on("End Of Service Gratuity", "onload", function(frm) {
    cur_frm.set_query("for_emp", function() {
        return {
            "filters": {
                "status": "Left"
            }
        };
    });
});



frappe.ui.form.on("End Of Service Gratuity","for_emp", function(frm) {
	console.log(frm.doc.for_emp );
	frappe.call({
				"method": "erpnext.hr.doctype.end_of_service_gratuity.end_of_service_gratuity.get_eos_reward",

				args: {selected_emp: frm.doc.for_emp,based_on_basic_salary: frm.doc.based_on_basic_salary,compelling_reasons:frm.doc.compelling_reasons },
				callback:function(data){
					console.log(data);
					cur_frm.set_value("gratuity",data.message[0]);
					cur_frm.set_value("duration_of_service",data.message[1]);
				}
			});


});

frappe.ui.form.on("End Of Service Gratuity","based_on_basic_salary", function(frm) {
	frappe.call({
				"method": "erpnext.hr.doctype.end_of_service_gratuity.end_of_service_gratuity.get_eos_reward",

				args: {selected_emp: frm.doc.for_emp,based_on_basic_salary: frm.doc.based_on_basic_salary,compelling_reasons:frm.doc.compelling_reasons },
				callback:function(data){
					console.log(data);
					cur_frm.set_value("gratuity",data.message[0]);
					cur_frm.set_value("duration_of_service",data.message[1]);
				}
			});


});

// frappe.ui.form.on("End Of Service Gratuity","compelling_reasons", function(frm) {
// 	frappe.call({
// 				"method": "erpnext.hr.doctype.end_of_service_gratuity.end_of_service_gratuity.get_eos_reward",
//
// 				args: {selected_emp: frm.doc.for_emp,based_on_basic_salary: frm.doc.based_on_basic_salary,compelling_reasons:frm.doc.compelling_reasons },
// 				callback:function(data){
// 					console.log(data);
// 					cur_frm.set_value("gratuity",data.message[0]);
// 					cur_frm.set_value("duration_of_service",data.message[1]);
// 				}
// 			});
//
//
// });