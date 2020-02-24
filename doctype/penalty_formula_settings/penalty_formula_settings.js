// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Penalty Formula Settings', {
	refresh: function(frm) {

	},
	onload:function(frm){
		frm.set_query("fs_value_of", function() {
			return {
				filters: {
					type: "earning"
				}
			}
		});
		
		frm.set_query("sd_value_of", function() {
			return {
				filters: {
					type: "earning"
				}
			}
		});
		
		frm.set_query("td_value_of", function() {
			return {
				filters: {
					type: "earning"
				}
			}
		});
		
		frm.set_query("ft_value_of", function() {
			return {
				filters: {
					type: "earning"
				}
			}
		});
	},
	validate:function (frm) {
		calculate_all(cur_frm);
	}
});


var calculate_all = function(cur_frm) {
	calculate_first_formula(cur_frm);
	calculate_Second_formula(cur_frm);
	calculate_third_formula(cur_frm);
	calculate_fourth_formula(cur_frm);
}


function calculate_first_formula(cur_frm) {
	var F1 = cur_frm.doc.fs_value ,F2 =cur_frm.doc.fs_value_type ,F3 = cur_frm.doc.fs_value_of ;
	if(F1 && F2 && F3)
	{
		CalculateFormula(F1,F2,F3,"fs_formula");
	}
}
function calculate_Second_formula(cur_frm) {
	var F1 = cur_frm.doc.sd_value ,F2 =cur_frm.doc.sd_value_type ,F3 = cur_frm.doc.sd_value_of ;
	if(F1 && F2 && F3)
	{
		CalculateFormula(F1,F2,F3,"sd_formula");
	}
}
function calculate_third_formula(cur_frm) {
	var F1 = cur_frm.doc.td_value ,F2 =cur_frm.doc.td_value_type ,F3 = cur_frm.doc.td_value_of ;
	if(F1 && F2 && F3)
	{
		CalculateFormula(F1,F2,F3,"td_formula");
	}
}
function calculate_fourth_formula(cur_frm) {
	var F1 = cur_frm.doc.ft_value ,F2 =cur_frm.doc.ft_value_type ,F3 = cur_frm.doc.ft_value_of ;
	if(F1 && F2 && F3)
	{
		CalculateFormula(F1,F2,F3,"ft_formula");
	}
}


function CalculateFormula(F1,F2,F3,F4){
	var Value_Type_Dic = {
		"Days":"("+ F3 + " / 30) * " + F1,
		"Percentage":"("+F1 + " / 100) * " + F3,
		"Amount": F1
	}

	cur_frm.set_value(F4,Value_Type_Dic[F2]);
}

