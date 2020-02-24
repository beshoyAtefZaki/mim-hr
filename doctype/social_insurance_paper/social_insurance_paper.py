# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class SocialinsurancePaper(Document):
	def validate (self):
		pass
		# self.append("social_insurance_data",
		# 	{
		# 	"employee": self.employee,
		# 	"subscription_number": self.subscription_number,
		# 	"subscription_date": self.subscription_start_date,
		# 	"expiry_date": self.expiry_date,
		# 	"subscription_status":self.subscription_status
		# 	})



@frappe.whitelist()
def set_amount(salary_st , compo):
		return (frappe.db.sql("""
					SELECT amount AS amount FROM `tabSalary Detail`
					 WHERE parent=%s AND
					 salary_component=%s
		
		
					""",( salary_st,compo)) 
		)