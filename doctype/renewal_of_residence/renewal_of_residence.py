# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
#my updated
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import datetime
from dateutil.relativedelta import relativedelta
class Renewalofresidence(Document):
	def fill_employee_details(self):
		return (frappe.db.sql(""" 
		
					SELECT name AS name ,
					employee AS employee , employee_name AS employee_name ,
					general_number AS general_number , 
					residence_number AS residence_number ,
					boarder_number AS boarder_number ,  
					work_license_number AS work_license_number , 

					end_date AS end_date ,start_date as start_date
					FROM `tabResidence Data` WHERE end_date BETWEEN %s
					AND %s AND docstatus=1
		
					""",(self.from_date , self.to_date ),as_dict=True)
				)
		
	def make_payment(self):
		precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")
		journal_entry = frappe.new_doc('Journal Entry')
		journal_entry.voucher_type = 'Journal Entry'
		journal_entry.user_remark = ("Social insurance Renew")
			
		journal_entry.company = self.company
		journal_entry.posting_date = self.posting_date
		total_amount = self.total_amount
		residence_renew_default_account = frappe.get_cached_value('Company',
			{"company_name": self.company},  "default_residence_renew")

		if not residence_renew_default_account:
			frappe.throw(_("Please set Default Residence Renew Account in Company {0}")
				.format(self.company))
		for i in self.employee :	
			journal_entry.append("accounts",
					{
					"account": residence_renew_default_account,
					"party_type" : "Employee",
					"party" : i.employee ,
					"debit_in_account_currency": total_amount,
					"cost_center":self.cost_center,
					"description" : "residence renew for %s"%i.emplyee_name

					},

				)
		journal_entry.append("accounts",
			{
			"account": self.payment_account,
			"credit_in_account_currency": total_amount,
			"reference_type": self.doctype,
			"cost_center":self.cost_center
			})
		

		journal_entry.save(ignore_permissions = True)
		self.has_gl=1
		self.save()
	def renew_all(self):
		for i in self.employee :
			# data = frappe.db.sql(""" SELECT start_date , end_date,
			# 	residence_number,work_license_number , work_license_fee ,
			# 	residence_renewal_fee FROM `tabResidence Data` WHERE employee=%s"""%i.employee)
			# if data :
			# frappe.throw(i.parent1)
			doc = frappe.get_doc("Residence Data",str(i.parent1))
				
			doc.append("history",{
				"start_date":doc.start_date ,
				"end_date":doc.end_date ,
				"residence_number" : doc.residence_number,
				"work_license_number":doc.work_license_number,
				"work_license_fee":doc.work_license_fee,
				"re_renew":doc.residence_renewal_fee,
				})
			# doc.start_date = 
			# date        = datetime.datetime.strptime(doc.end_date, "%Y-%m-%d")
			date        = doc.end_date
			doc.start_date    = date + relativedelta(days =+ 1)
			doc.end_date = date + relativedelta(days =+ 365)
			doc.residence_number = i.resident_no
			doc.work_license_number = i.employee_business_license
			doc.work_license_fee = i.business_license_price
			doc.residence_renewal_fee = i.resident_price
			# doc.insert(ignore_permissions=True)
			doc.save(ignore_permissions=True)
			self.completed = 1
			self.docstatus= 1
			self.save()
			frappe.db.commit()
