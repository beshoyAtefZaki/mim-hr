// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Renewal of residence', {


	onload:function(frm){
		if(frm.doc.completed== 1 ){
				frm.page.clear_primary_action();
		}

	},
	refresh: function(frm) {
		if(frm.doc.completed== 1 ){
				frm.page.clear_primary_action();
		}
		if (frm.doc.docstatus == 0 & frm.doc.employee.length== 0) {
			if(!frm.is_new()) {
				frm.page.clear_primary_action();
				frm.add_custom_button(__("Get Employees"),
					function() {
						frm.events.get_employee_details(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);
			}
		
		}
		if (frm.doc.docstatus == 0 & frm.doc.employee.length != 0 & frm.doc.has_gl==0) {
			if(!frm.is_new()) {
				frm.page.clear_primary_action();
				frm.add_custom_button(__("Make Payment"),
					function() {
						frm.events.make_payment(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);
			}
		
		}
		if (frm.doc.completed != 1 & frm.doc.employee.length != 0 & frm.doc.has_gl==1) {
			if(!frm.is_new()) {
				frm.page.clear_primary_action();
				frm.add_custom_button(__("Renew all"),
					function() {
						frm.events.renew_all(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);
			}
		
		}
		
	},
	renew_all :function(frm){
		return frappe.call({
				doc: frm.doc,
				method: 'renew_all',
				callback: function(r){

				frm.page.clear_primary_action();

				} 

			})

	},
	make_payment:function(frm){
		console.log("ok")
		return frappe.call({
				doc: frm.doc,
				method: 'make_payment',
				callback: function(r){

					frappe.set_route(
					'List', 'Journal Entry', {"Journal Entry Account.reference_name": frm.doc.name}
				);
				} 

			})
	},

	get_employee_details : function(frm){

				return frappe.call({
				doc: frm.doc,
				method: 'fill_employee_details',
				callback: function(r) {
				console.log(r.message)
				var i ;
				for (i=0 ; i < r.message.length ; i++){
					var child = frm.add_child("employee");
					frappe.model.set_value( child.doctype, child.name,"parent1",
						r.message[i].name)
					frappe.model.set_value( child.doctype, child.name,"employee",
						r.message[i].employee)

					frappe.model.set_value( child.doctype, child.name,"emplyee_name",
						r.message[i].employee_name)

					frappe.model.set_value( child.doctype, child.name,"employee_general_number",
						r.message[i].general_number)

					frappe.model.set_value( child.doctype, child.name,"employee_business_license",
						r.message[i].work_license_number )

					frappe.model.set_value( child.doctype, child.name,"employee_border_number",
						r.message[i].boarder_number)
					
					frappe.model.set_value( child.doctype, child.name,"resident_no",
						r.message[i].residence_number)
					frappe.model.set_value( child.doctype, child.name,"the_expiry_date",
						r.message[i].end_date)
					frm.save()
					frm.refresh_field("employee")

				}
			}


			})
	}
});


frappe.ui.form.on('Renewal of residence Table', {
refresh:function(frm, cdt, cdn){
var loacl = locals[cdt][cdn]
	console.log("here")
	if (!frm.doc.employee.length) {
		frm.set_value("total_amount" , 0)
		frm.refresh_field("total_amount")

	}
	var total = 0
	var i ;
	for(i =0 ; i < frm.doc.employee.length ; i++){
		if (frm.doc.employee[i].business_license_price){
				total += frm.doc.employee[i].business_license_price ;}
		if(frm.doc.employee[i].resident_price){		
				total += frm.doc.employee[i].resident_price ;}
	}
	
	frm.set_value("total_amount" ,total)
	frm.refresh_field("total_amount")
},


business_license_price:function(frm, cdt, cdn){
	var loacl = locals[cdt][cdn]
	console.log("here")
	var total = 0
	var i ;
	for(i =0 ; i < frm.doc.employee.length ; i++){
		if (frm.doc.employee[i].business_license_price){
				total += frm.doc.employee[i].business_license_price ;}
		if(frm.doc.employee[i].resident_price){		
				total += frm.doc.employee[i].resident_price ;}
	}
	
	frm.set_value("total_amount" ,total)
	frm.refresh_field("total_amount")
},
resident_price:function(frm, cdt, cdn){
	var loacl = locals[cdt][cdn]
	var total = 0
	var i ;
	for(i =0 ; i < frm.doc.employee.length ; i++){
		if (frm.doc.employee[i].business_license_price){
				total += frm.doc.employee[i].business_license_price ;}
		if(frm.doc.employee[i].resident_price){		
				total += frm.doc.employee[i].resident_price ;}
	}
	frappe.model.set_value(cdt,cdn,"total_amount" ,total)
	frm.set_value("total_amount" ,total)
	frm.refresh_field("total_amount")

}



})