// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Social insurance Paper', {
	// onload: function (frm) {

	// 	// frm.set_query("employee", function() {
	// 	// 	return {
	// 	// 		"filters": {
	// 	// 			"citizen_or_resident": "Citizen",
	// 	// 		}
	// 	// 	};

	// 	// })
	// },
	expiry_date: function(frm) {
    console.log(frm.doc.expiry_date)
	},
	employee:function(frm){
			frappe.call({
			method:"frappe.client.get_value",
			args:{
				doctype:"Salary Structure Assignment",
				filters: {
					employee : frm.doc.employee
				},
			fieldname:["salary_structure"] ,
		},
		callback:function(r){
			console.log(r.message.salary_structure)
			var s_t = r.message.salary_structure
			frm.set_value("salary_structure" , s_t )
			}
			
		

			


		})
	}
});







frappe.ui.form.on('Salary Detail', {
	amount: function(frm, cdt, cdn){
		
		// var local = locals[cdt][cdn];
		// var amount = frm.doc.monthly_amount
		// amount += local.amount
		// var test_amount = amount * 0.10
		// frm.set_value("monthly_amount" , 0)
		var total = 0
		var i ;
		if(frm.doc.citizen_or_resident == "Citizen")
		{for (i=0 ; i < frm.doc.salary_component.length ; i ++){
					var amount = frm.doc.salary_component[i].amount
					var rate = frm.doc.salary_component[i].amount * 0.12
					total += rate
		
				}
				}
		if(frm.doc.citizen_or_resident == "Resident")
		{for (i=0 ; i < frm.doc.salary_component.length ; i ++){
					var amount = frm.doc.salary_component[i].amount
					var rate = frm.doc.salary_component[i].amount * 0.2
					total += rate
		
				}
				}
		frm.set_value("monthly_amount" , total)
	},

	salary_component: function(frm ,cdt,cdn){
		var local = locals[cdt][cdn];
		// console.log(local.salary_component)
		// console.log(frm.doc.employee)
		if(local.salary_component){
				frappe.call({
						method:"erpnext.hr.doctype.social_insurance_paper.social_insurance_paper.set_amount",
						args :{
							"salary_st":frm.doc.salary_structure,
							"compo":local.salary_component
						},
				
				callback:function(r){
					if(r.message.length > 0 ){
								console.log(r.message[0][0])
								
								frappe.model.set_value(cdt,cdn,"amount" ,r.message[0][0]);}
					
					}
					
		
				})}

	},
	get_employee_details:function(frm){
		console.log("here")
	}




})