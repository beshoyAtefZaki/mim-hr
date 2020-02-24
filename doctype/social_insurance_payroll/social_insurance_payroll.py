# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class SocialinsurancePayroll(Document):


	def get_salary_componant(self,employee):	

		co_salary_sturcture = frappe.db.sql("""
			SELECT salary_structure FROM `tabSalary Structure Assignment` WHERE employee =%s

			""" ,employee)

		return co_salary_sturcture
	def get_employee (self):
		data = []
		resident_employee = frappe.db.sql("""SELECT name AS name FROM `tabEmployee` WHERE
							citizen_or_resident ='Resident' 
							AND status = 'Active'  """)
		citizen_employee = frappe.db.sql("""SELECT name AS name FROM `tabEmployee` WHERE 
							citizen_or_resident ='Citizen' 
							AND status = 'Active'  """)


		resident_type = frappe.db.sql(""" 
			SELECT salary_component AS salary_component , percent AS percent FROM 
			`tabSocial insurance Settings Table`  WHERE type = 'Resident'
				""" ,as_dict=1)

		citizen_type = frappe.db.sql(""" 
			SELECT salary_component AS salary_component , percent AS percent FROM 
			`tabSocial insurance Settings Table`  WHERE type = 'Citizen'
				""" ,as_dict=1)
		for employee in resident_employee :
			salaery_st = self.get_salary_componant(employee[0])
			if salaery_st :
				
				salary_data = frappe.db.sql("""SELECT  %s  WHERE  """)
			else :
				return("NONE")
		# return (resident_type[0]['salary_component'])
	