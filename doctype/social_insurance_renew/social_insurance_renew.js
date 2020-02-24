// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Social insurance Renew', {
	onload: function(frm) {
				
			if(!frm.is_new()) {
				frm.page.clear_primary_action();
				frm.add_custom_button(__("Get Employees"),
					function() {
						frm.events.get_employee_details(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);
			

			
		}
		// if(frm.doc.docstatus == 0 && frm.doc.social_insurance_date.length != 0){
		// 	console.log("two")
		// 	frm.page.clear_primary_action();
		// 	frm.add_custom_button(("Make Payment"),
		// 		function() {
		// 				frm.events.get_employee_details(frm);
		// 			} ).toggleClass('btn-primary');

		// }

	},


		refresh: function(frm) {
		if(!frm.is_new() && frm.doc.social_insurance_date.length == 0 ) {
				frm.page.clear_primary_action();
				frm.add_custom_button(__("Get Employees"),
					function() {
						frm.events.get_employee_details(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);
			

			
		}
				if(!frm.is_new() && frm.doc.social_insurance_date.length != 0 && frm.doc.has_gl==0) {
				frm.page.clear_primary_action();
				frm.add_custom_button(__("Make Payment"),
					function() {
						frm.events.make_payment(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);
			

			
		}

		if (frm.doc.has_gl ==1){
			frm.page.clear_primary_action();
				frm.add_custom_button(__("Update Employee Data"),
					function() {
						frm.events.update_employee_data(frm);
					}
				).toggleClass('btn-primary', !(frm.doc.employees || []).length);

		}

			
		},
		
	// },
		update_employee_data(frm){
			return frappe.call({
				doc: frm.doc,
				method : 'update_employee',
				callback:function(r){
					console.log(r)
					frm.refresh();
					

				}

			})
		},
		make_payment:function(frm){
			console.log("here")
			return frappe.call({
				doc: frm.doc,
				method : 'make_payment',
				callback:function(r){
					console.log(r)
					frm.refresh();

				

				}
			})
		},
	
		get_employee_details : function (frm) {
			return frappe.call({
				doc: frm.doc,
				method: 'fill_employee_details',
			callback: function(r) {
				// console.log(r.message)
				var i ;
				for (i=0 ; i < r.message.length ; i++){
					var child = frm.add_child("social_insurance_date");
					frappe.model.set_value( child.doctype, child.name,"employee",
						r.message[i].employee)

					frappe.model.set_value( child.doctype, child.name,"employee_name",
						r.message[i].employee_name)

					frappe.model.set_value( child.doctype, child.name,"general_number",
						r.message[i].employee_general_number)

					frappe.model.set_value( child.doctype, child.name,"insurance_number",
						r.message[i].subscription_number)

					frappe.model.set_value( child.doctype, child.name,"end_date",
						r.message[i].expiry_date)
					
					frappe.model.set_value( child.doctype, child.name,"amount_for_month",
						r.message[i].monthly_amount)
					frm.save()
					frm.refresh_field("social_insurance_date")

				}
			}


			})
	}
	}

	
						);



// let get_employee_details = function (frm) {
// 		console.log("ok")
// 	}