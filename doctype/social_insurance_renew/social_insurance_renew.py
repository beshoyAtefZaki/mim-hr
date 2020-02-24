# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import datetime
from dateutil.relativedelta import relativedelta
class SocialinsuranceRenew(Document):
	def fill_employee_details(self):
		# return(self.from_date)
		return (frappe.db.sql(""" 
		
					SELECT 
					employee AS employee , employee_name AS employee_name ,
					employee_general_number AS employee_general_number , 
					expiry_date AS expiry_date , monthly_amount AS monthly_amount,
					subscription_number AS subscription_number
					FROM `tabSocial insurance Paper` WHERE expiry_date BETWEEN %s
					AND %s
		
					""",(self.from_date , self.to_date ),as_dict=True)
				)
		# return (frappe.db.sql(""" 
		
		# 			SELECT *
		# 			FROM `tabSocial insurance Paper` WHERE expiry_date=%s
		# 		"""%self.to_date) )

	def update_employee(self):
		for employee in self.social_insurance_date :
			# date = employee.end_date
			date =datetime.datetime.strptime(employee.end_date, "%Y-%m-%d")
			
			start_date = date +  relativedelta(days =+ 1) 
			end_date    = start_date  + relativedelta(months =+ 1) 
			frappe.db.sql(""" UPDATE `tabSocial insurance Paper` 
				SET  subscription_start_date =%s  ,
				 expiry_date =%s WHERE employee =%s 
				""",(start_date,end_date,str(employee.employee)))
			frappe.db.commit()
		return ("done")
	def make_payment(self):
				
		# default_payroll_payable_account = self.get_default_payroll_payable_account()
		precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")
		journal_entry = frappe.new_doc('Journal Entry')
		journal_entry.voucher_type = 'Journal Entry'
		journal_entry.user_remark = ("Social insurance Renew")
			
		journal_entry.company = self.company
		journal_entry.posting_date = self.posting_date
		total_amount = 0.0
		for amount in self.social_insurance_date:
			total_amount +=  float(amount.amount_for_month)
			
			
			journal_entry.append("accounts",
					{
					"account": self.account,
					"debit_in_account_currency": float(amount.amount_for_month),
					"party_type":"Employee",
					"party":amount.employee,
					"cost_center":self.cost_center

					},

			)
		journal_entry.append("accounts",
			{
			"account": self.paid_account,
			"credit_in_account_currency": total_amount,
			"reference_type": self.doctype,
			"cost_center":self.cost_center
			})




	
		journal_entry.save(ignore_permissions = True)
		self.has_gl ="1"
		self.save()
		return ("done")







@frappe.whitelist()
def get_employee_details(name):
	pass
