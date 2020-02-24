# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.model.delete_doc import delete_doc

class EmployeeProjectManagement(Document):
	def validate(self):
		pass

	def on_submit(self):
		# parent = frappe.get_doc("Employee", self.employee)
		# child = frappe.new_doc('Projects')
		# child.update({
		# 			"parent_type":"Employee",
		# 			"parent":self.employee,
		# 			"project":self.new_project,
		# 			"start_date":self.start_from,
		# 			"end_date":self.end_in,
		# 			"remark":self.reason
		# 			  })
		# parent.append('projects', child)
		# parent.save()

		emp = frappe.get_doc('Employee', self.employee)
		new_project = frappe.new_doc('Projects')

		new_project.update({
			"parent_type":"Employee",
			"parent":self.employee,
			"project":self.new_project,
			"start_date":self.start_from,
			"end_date":self.end_in,
			"employee_project_reference":self.name,
			"remark":self.reason
		})

		emp.append('projects',new_project)
		emp.save()

	def on_cancel(self):
		doc_name = frappe.db.get_value("Projects",{"employee_project_reference":self.name},"name")

		frappe.delete_doc("Projects",doc_name)

	def get_employee_project(self):

		old_project = frappe.get_list("Projects",filters={"parent":self.employee},fields=["project","start_date","end_date"],order_by="start_date desc",limit_page_length=1)
		if old_project:
			return old_project [0]
