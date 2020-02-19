# -*- coding: utf-8 -*-
# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import datetime
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, flt
from erpnext.hr.utils import set_employee_name
from erpnext.hr.doctype.leave_application.leave_application import get_leave_balance_on
from erpnext.hr.doctype.salary_structure_assignment.salary_structure_assignment import get_assigned_salary_structure


class LeaveEncashment(Document):
	encashable_days_from_out = 0.0
	encasha_amount_from_out = 0.0
	def __init__(self, *args, **kwargs):
		super(LeaveEncashment, self).__init__(*args, **kwargs)
		self.series = 'Sal Slip/{0}/.#####'.format(self.employee)
		self.whitelisted_globals = {
			"int": int,
			"float": float,
			"long": int,
			"round": round,
			"date": datetime.date,
			"getdate": getdate
		}
	
	def validate(self):
		set_employee_name(self)
		self.get_leave_details_for_encashment(self.encashable_days,encashment_amount=self.encashment_amount)
		
		if not self.encashment_date:
			self.encashment_date = getdate(nowdate())
	
	def before_submit(self):
		if self.encashment_amount <= 0:
			frappe.throw(_("You can only submit Leave Encashment for a valid encashment amount"))
	
	def on_submit(self):
		if not self.leave_allocation:
			self.leave_allocation = self.get_leave_allocation()
		additional_salary = frappe.new_doc("Additional Salary")
		additional_salary.company = frappe.get_value("Employee", self.employee, "company")
		additional_salary.employee = self.employee
		additional_salary.salary_component = frappe.get_value("Leave Type", self.leave_type, "earning_component")
		additional_salary.payroll_date = self.encashment_date
		additional_salary.amount = self.encashment_amount
		additional_salary.submit()
		
		self.db_set("additional_salary", additional_salary.name)
		
		# Set encashed leaves in Allocation
		frappe.db.set_value("Leave Allocation", self.leave_allocation, "total_leaves_encashed",
		                    frappe.db.get_value('Leave Allocation', self.leave_allocation,
		                                        'total_leaves_encashed') + self.encashable_days)
	
	def on_cancel(self):
		if self.additional_salary:
			frappe.get_doc("Additional Salary", self.additional_salary).cancel()
			self.db_set("additional_salary", "")
		
		if self.leave_allocation:
			frappe.db.set_value("Leave Allocation", self.leave_allocation, "total_leaves_encashed",
			                    frappe.db.get_value('Leave Allocation', self.leave_allocation,
			                                        'total_leaves_encashed') - self.encashable_days)
	
	def get_leave_details_for_encashment(self, current_days=0.0,encashment_amount=0.0):
		self.encasha_amount_from_out = encashment_amount
		self.salary_structure = get_assigned_salary_structure(self.employee, self.encashment_date or getdate(nowdate()))
		if not self.salary_structure:
			frappe.throw(_("No Salary Structure assigned for Employee {0} on given date {1}").format(self.employee,
			                                                                                         self.encashment_date))
		
		if not frappe.db.get_value("Leave Type", self.leave_type, 'allow_encashment'):
			frappe.throw(_("Leave Type {0} is not encashable").format(self.leave_type))
		
		self.leave_balance = get_leave_balance_on(self.employee, self.leave_type,
		                                          self.encashment_date or getdate(nowdate()),
		                                          consider_all_leaves_in_the_allocation_period=True)

		if flt(current_days) > 0:
			encashable_days = current_days
			self.encashable_days_from_out = current_days
		else:
			encashable_days = ((self.leave_balance - frappe.db.get_value('Leave Type', self.leave_type,
			                                                             'encashment_threshold_days')) if self.encashable_days_from_out == 0.0 else self.encashable_days_from_out)
		# frappe.msgprint(str(self.encashment_amount))
		if encashment_amount == None:#or encashment_amount != self.encashment_amount:

			self.encashable_days = flt(encashable_days) if flt(encashable_days) > 0 else 0
			day_calculation = 360 # frappe.db.get_single_value("HR Settings", "day_calculation")
			if day_calculation == "Calendar":
				day_calculation = "365"
			day_percentage = 12 / flt(day_calculation)
			per_day_encashment = 0.0
			data = self.get_data_for_eval()
			salary_components = data["salary_components"]
			# frappe.msgprint(str(salary_components))
			for key in salary_components:
				check_add = frappe.db.get_value("Salary Component", key["salary_component"], "include_in_leave_encashment_")
				if check_add == 1:
					if key["amount_based_on_formula"] == 1 and key["amount_based_on_func"] == 0:
						formula = key["formula"].strip() if key["formula"] else None
						if formula:
							# frappe.msgprint(str(formula))
							per_day_encashment += frappe.safe_eval(formula, self.whitelisted_globals, data)
					elif key["amount_based_on_func"] == 0:
						per_day_encashment += flt(key["amount"])
			
				self.encashment_amount = self.encashable_days * day_percentage * per_day_encashment if per_day_encashment > 0 else 0
		else:
			self.encashment_amount = encashment_amount
			
		self.leave_allocation = self.get_leave_allocation()
		return True
	
	def get_leave_allocation(self):
		leave_allocation = frappe.db.sql("""select name from `tabLeave Allocation` where '{0}'
		between from_date and to_date and docstatus=1 and leave_type='{1}'
		and employee= '{2}'""".format(self.encashment_date or getdate(nowdate()), self.leave_type, self.employee))
		
		return leave_allocation[0][0] if leave_allocation else None
	
	def get_data_for_eval(self):
		'''Returns data for evaluating formula'''
		data = frappe._dict()
		
		data.update(frappe.get_doc("Salary Structure Assignment",
		                           {"employee": self.employee, "salary_structure": self.salary_structure}).as_dict())
		
		# set values for components
		salary_components = frappe.get_list("Salary Detail",
		                                    filters={"parent": self.salary_structure, "parentfield": "earnings"},
		                                    fields=["parentfield", "amount", "amount_based_on_formula", "formula",
		                                            "statistical_component", "`condition`", "salary_component",
		                                            "amount_based_on_func"])
		if salary_components:
			data["salary_components"] = salary_components
		
		return data
