# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from dateutil.relativedelta import relativedelta

from frappe.utils import getdate, validate_email_add, today, add_years, format_datetime, add_days, cstr
from frappe.model.naming import set_name_by_naming_series
from frappe import throw, _, scrub
from frappe.permissions import add_user_permission, remove_user_permission, \
	set_user_permission_if_allowed, has_permission
from datetime import datetime
from frappe.model.document import Document
from erpnext.utilities.transaction_base import delete_events
from frappe.utils.nestedset import NestedSet
from frappe.utils.background_jobs import enqueue

class EmployeeUserDisabledError(frappe.ValidationError): pass
class EmployeeLeftValidationError(frappe.ValidationError): pass
class OverlapError(frappe.ValidationError): pass
from pandas.core.dtypes.common import is_integer

class Employee(NestedSet):
	nsm_parent_field = 'reports_to'

	# def autoname(self):
	# 	naming_method = frappe.db.get_value("HR Settings", None, "emp_created_by")
	# 	if not naming_method:
	# 		throw(_("Please setup Employee Naming System in Human Resource > HR Settings"))
	# 	else:
	# 		if naming_method == 'Naming Series':
	# 			set_name_by_naming_series(self)
	# 		elif naming_method == 'Employee Number':
	# 			self.name = self.employee_number
	# 		elif naming_method == 'Full Name':
	# 			self.set_employee_name()
	# 			self.name = self.employee_name
	#
	# 	self.employee = self.name

	def validate(self):
		from erpnext.controllers.status_updater import validate_status
		validate_status(self.status, ["Active", "Temporary Leave", "Left"])

		if self.date_of_birth and getdate(self.date_of_birth) > getdate(today()):
			throw(_("Date of Birth cannot be greater than today."))

		min_age_for_emp = int(frappe.db.get_single_value("HR Settings", "min_age_for_emp") or 18)
		if relativedelta(getdate(today()), getdate(self.date_of_birth)).years < min_age_for_emp:
			throw(_("Employee Age should be greater than {0}").format(min_age_for_emp))

		if self.date_of_birth and self.date_of_joining and getdate(self.date_of_birth) >= getdate(self.date_of_joining):
			throw(_("Date of Joining must be greater than Date of Birth"))

		elif self.date_of_retirement and self.date_of_joining and (
				getdate(self.date_of_retirement) <= getdate(self.date_of_joining)):
			throw(_("Date Of Retirement must be greater than Date of Joining"))

		elif self.relieving_date and self.date_of_joining and (
				getdate(self.relieving_date) <= getdate(self.date_of_joining)):
			throw(_("Relieving Date must be greater than Date of Joining"))

		elif self.contract_end_date and self.date_of_joining and (
				getdate(self.contract_end_date) <= getdate(self.date_of_joining)):
			throw(_("Contract End Date must be greater than Date of Joining"))

		elif self.reason_for_resignation in ["Married", "Have Baby"] and not self.marital_status_date:
			throw(_("Please enter Marital Status Date"))
		elif(self.citizen_or_resident=="Citizen" and len(self.id_number) != 10):
			throw(_("ID Number Must Be Ten Number."))
		elif(frappe.db.get_value("Employee", self.id_number, "id_number")):
			throw(_("ID Number is Already Exist..."))
		elif(is_integer(self.id_number)):
			throw(_("ID Number is Already Exist..."))

		self.employee = self.name
		self.set_employee_name()
		self.validate_date()
		self.validate_email()
		self.validate_status()
		self.validate_employee_leave_approver()
		self.validate_reports_to()
		self.validate_preferred_email()
		self.validate_stop_working_date()
		self.validate_medical_data()
		#self.validate_resident_data()
		self.validate_attendance_data()
		if self.job_applicant:
			self.validate_onboarding_process()

		if self.user_id:
			self.validate_user_details()
		else:
			existing_user_id = frappe.db.get_value("Employee", self.name, "user_id")
			if existing_user_id:
				remove_user_permission(
					"Employee", self.name, existing_user_id)
		if self.finger_print_number:
		    self.validate_duplicate_finger_print_number()

	def set_employee_name(self):
		self.employee_name = ' '.join(filter(lambda x: x, [self.first_name, self.middle_name, self.last_name]))

	def validate_user_details(self):
		data = frappe.db.get_value('User',
			self.user_id, ['enabled', 'user_image'], as_dict=1)
		if data.get("user_image"):
			self.image = data.get("user_image")
		self.validate_for_enabled_user_id(data.get("enabled", 0))
		self.validate_duplicate_user_id()

	def validate_stop_working_date(self):
		stop_working_dict = self.get("stop_working_data")
		for item in stop_working_dict:
			tem_pdate = add_days(datetime.strptime(item.start_date, '%Y-%m-%d'), 180)
			if (datetime.strptime(item.start_date, '%Y-%m-%d') > datetime.strptime(item.end_date, '%Y-%m-%d')):
				frappe.throw(_("Start Date should not exceed End Date"), title=_("STOP WORKING DATA"))
			elif (datetime.strptime(item.end_date, '%Y-%m-%d') > tem_pdate):
				frappe.throw(_("End Date should not exceed than 180 day"), title=_("STOP WORKING DATA"))
			elif (item.cut_percentage != ""):
				if (float(item.cut_percentage) > 50):
					frappe.throw(_("Cut percentage should not exceed than 50%"), title=_("STOP WORKING DATA"))

			existing = self.check_stop_working_dates(item)
			if existing:
				frappe.throw(_("You have overlap in Row {0}: Start From and End Date of {1} ")
							 .format(item.idx, self.name), OverlapError, title=_("STOP WORKING DATA"))

	def validate_medical_data(self):
		employee_medical_documents = self.get("employee_medical_documents")
		for item in employee_medical_documents:
			if item.start_date and item.end_date:
				if (datetime.strptime(item.start_date, '%Y-%m-%d') > datetime.strptime(item.end_date, '%Y-%m-%d')):
					frappe.throw(_("Start Date  should not exceed End Date"), title=_("MEDICAL DOCUMENTS"))
			existing = self.check_medical_data_dates(item)
			if existing:
				frappe.throw(_("You have overlap in Row {0}: Start Date and End Date of {1} ")
							 .format(item.idx, self.name), OverlapError, title=_("MEDICAL DOCUMENTS"))

	def check_medical_data_dates(self, item):
		# check internal overlap
		for employee_medical_document in self.employee_medical_documents:
			# end_date = employee_medical_document.end_date
			if not employee_medical_document.end_date:
				if item.idx != employee_medical_document.idx and (employee_medical_document.start_date < item.end_date):
					return self

			if (item.idx != employee_medical_document.idx) and employee_medical_document.end_date and (
					(
							item.start_date > employee_medical_document.start_date and item.start_date < employee_medical_document.end_date) or
					(
							item.end_date > employee_medical_document.start_date and item.end_date < employee_medical_document.end_date) or
					(
							item.start_date <= employee_medical_document.start_date and item.end_date >= employee_medical_document.end_date)):
				return self

	def check_stop_working_dates(self, item):
		# check internal overlap
		for stop_working in self.stop_working_data:

			if item.idx != stop_working.idx and (
					(
							item.start_date > stop_working.start_date and item.start_date < stop_working.end_date) or
					(
							item.end_date > stop_working.start_date and item.end_date < stop_working.end_date) or
					(
							item.start_date <= stop_working.start_date and item.end_date >= stop_working.end_date)):
				return self

	def validate_resident_data(self):
		employee_resident_data = self.get("employee_resident_data")
		for item in employee_resident_data:
			if (datetime.strptime(item.release_start_date, '%Y-%m-%d') > datetime.strptime(item.release_end_date,
																						   '%Y-%m-%d')):
				frappe.throw(_("Release Start Date should not exceed Release End Date"), title=_("RESIDENT DATA"))

			existing = self.check_resident_dates(item)
			if existing:
				frappe.throw(_("You have overlap in Row {0}: Release Start Date and Release End Date of {1} ")
							 .format(item.idx, self.name), OverlapError, title=_("RESIDENT DATA"))

	def validate_attendance_data(self):
		employee_attendance_data = self.get("employee_attendance_data")
		if employee_attendance_data:
			for item in employee_attendance_data:
				period_start_date = frappe.db.get_value("Attendance Period", {"period_name": item.attendance_period},
														"start_date")
				period_end_date = frappe.db.get_value("Attendance Period", {"period_name": item.attendance_period},
													  "end_date")

				if (datetime.strptime(item.start_date, '%Y-%m-%d') < datetime.strptime(cstr(period_start_date),
																					   '%Y-%m-%d')):
					frappe.throw(_("Start Date should not be before Period Start Date"), title=_("ATTENDANCE DATA"))

				if item.end_date:
					if (datetime.strptime(item.end_date, '%Y-%m-%d') > datetime.strptime(cstr(period_end_date),
																						 '%Y-%m-%d')):
						frappe.throw(_("End Date should not exceed Period End Date"), title=_("ATTENDANCE DATA"))

					if (datetime.strptime(item.start_date, '%Y-%m-%d') > datetime.strptime(item.end_date, '%Y-%m-%d')):
						frappe.throw(_("Start Date should not exceed End Date"), title=_("ATTENDANCE DATA"))

				existing = self.check_attendance_dates(item)
				if existing:
					frappe.throw(_("You have overlap in Row {0}: Start Date and  End Date of {1} ")
								 .format(item.idx, self.name), OverlapError, title=_("ATTENDANCE DATA"))

	def check_attendance_dates(self, item):
		# check internal overlap
		for attendance_data in self.employee_attendance_data:
			# end_date = attendance_data.end_date
			if not attendance_data.end_date:
				if item.idx != attendance_data.idx and (attendance_data.start_date < item.end_date):
					return self

			if (item.idx != attendance_data.idx) and attendance_data.end_date and (
					(
							item.start_date > attendance_data.start_date and item.start_date < attendance_data.end_date) or
					(
							item.end_date > attendance_data.start_date and item.end_date < attendance_data.end_date) or
					(
							item.start_date <= attendance_data.start_date and item.end_date >= attendance_data.end_date)):
				return self

	def update_nsm_model(self):
		frappe.utils.nestedset.update_nsm(self)

	def on_update(self):
		self.update_nsm_model()
		if self.user_id:
			self.update_user()
			self.update_user_permissions()

	def update_user_permissions(self):
		if not self.create_user_permission: return
		if not has_permission('User Permission', ptype='write', raise_exception=False): return

		employee_user_permission_exists = frappe.db.exists('User Permission', {
			'allow': 'Employee',
			'for_value': self.name,
			'user': self.user_id
		})

		if employee_user_permission_exists: return

		add_user_permission("Employee", self.name, self.user_id)
		set_user_permission_if_allowed("Company", self.company, self.user_id)

	def update_user(self):
		# add employee role if missing
		user = frappe.get_doc("User", self.user_id)
		user.flags.ignore_permissions = True

		if "Employee" not in user.get("roles"):
			user.append_roles("Employee")

		# copy details like Fullname, DOB and Image to User
		if self.employee_name and not (user.first_name and user.last_name):
			employee_name = self.employee_name.split(" ")
			if len(employee_name) >= 3:
				user.last_name = " ".join(employee_name[2:])
				user.middle_name = employee_name[1]
			elif len(employee_name) == 2:
				user.last_name = employee_name[1]

			user.first_name = employee_name[0]

		if self.date_of_birth:
			user.birth_date = self.date_of_birth

		if self.gender:
			user.gender = self.gender

		if self.image:
			if not user.user_image:
				user.user_image = self.image
				try:
					frappe.get_doc({
						"doctype": "File",
						"file_name": self.image,
						"attached_to_doctype": "User",
						"attached_to_name": self.user_id
					}).insert()
				except frappe.DuplicateEntryError:
					# already exists
					pass

		user.save()

	def validate_date(self):
		if self.date_of_birth and getdate(self.date_of_birth) > getdate(today()):
			throw(_("Date of Birth cannot be greater than today."))

		if self.date_of_birth and self.date_of_joining and getdate(self.date_of_birth) >= getdate(self.date_of_joining):
			throw(_("Date of Joining must be greater than Date of Birth"))

		elif self.date_of_retirement and self.date_of_joining and (getdate(self.date_of_retirement) <= getdate(self.date_of_joining)):
			throw(_("Date Of Retirement must be greater than Date of Joining"))

		elif self.relieving_date and self.date_of_joining and (getdate(self.relieving_date) <= getdate(self.date_of_joining)):
			throw(_("Relieving Date must be greater than Date of Joining"))

		elif self.contract_end_date and self.date_of_joining and (getdate(self.contract_end_date) <= getdate(self.date_of_joining)):
			throw(_("Contract End Date must be greater than Date of Joining"))

	def validate_email(self):
		if self.company_email:
			validate_email_add(self.company_email, True)
		if self.personal_email:
			validate_email_add(self.personal_email, True)

	def validate_status(self):
		if self.status == 'Left':
			reports_to = frappe.db.get_all('Employee',
				filters={'reports_to': self.name}
			)
			if reports_to:
				link_to_employees = [frappe.utils.get_link_to_form('Employee', employee.name) for employee in reports_to]
				throw(_("Employee status cannot be set to 'Left' as following employees are currently reporting to this employee:&nbsp;")
					+ ', '.join(link_to_employees), EmployeeLeftValidationError)
			if not self.relieving_date:
				throw(_("Please enter relieving date."))

	def validate_for_enabled_user_id(self, enabled):
		if not self.status == 'Active':
			return

		if enabled is None:
			frappe.throw(_("User {0} does not exist").format(self.user_id))
		if enabled == 0:
			frappe.throw(_("User {0} is disabled").format(self.user_id), EmployeeUserDisabledError)

	def validate_duplicate_user_id(self):
		employee = frappe.db.sql_list("""select name from `tabEmployee` where
			user_id=%s and status='Active' and name!=%s""", (self.user_id, self.name))
		if employee:
			throw(_("User {0} is already assigned to Employee {1}").format(
				self.user_id, employee[0]), frappe.DuplicateEntryError)

	def validate_duplicate_finger_print_number(self):
		employee = frappe.db.sql_list("""select name from `tabEmployee` where
	        finger_print_number=%s and status='Active' and name!=%s""", (self.finger_print_number, self.name))
		if employee:
			throw(_("Finger Print Number {0} is already assigned to Employee {1}").format(
				self.finger_print_number, employee[0]), frappe.DuplicateEntryError)

	def validate_employee_leave_approver(self):
		for l in self.get("leave_approvers")[:]:
			if "Leave Approver" not in frappe.get_roles(l.leave_approver):
				frappe.get_doc("User", l.leave_approver).add_roles("Leave Approver")

	def validate_reports_to(self):
		if self.reports_to == self.name:
			throw(_("Employee cannot report to himself."))

	def on_trash(self):
		self.update_nsm_model()
		delete_events(self.doctype, self.name)
		if frappe.db.exists("Employee Transfer", {'new_employee_id': self.name, 'docstatus': 1}):
			emp_transfer = frappe.get_doc("Employee Transfer", {'new_employee_id': self.name, 'docstatus': 1})
			emp_transfer.db_set("new_employee_id", '')

	def validate_preferred_email(self):
		if self.prefered_contact_email and not self.get(scrub(self.prefered_contact_email)):
			frappe.msgprint(_("Please enter " + self.prefered_contact_email))

	def validate_onboarding_process(self):
		employee_onboarding = frappe.get_all("Employee Onboarding",
			filters={"job_applicant": self.job_applicant, "docstatus": 1, "boarding_status": ("!=", "Completed")})
		if employee_onboarding:
			doc = frappe.get_doc("Employee Onboarding", employee_onboarding[0].name)
			doc.validate_employee_creation()
			doc.db_set("employee", self.name)

	def Check_project_reference(self,row_name):
		return frappe.get_value("Projects",row_name,"employee_project_reference")

def get_timeline_data(doctype, name):
	'''Return timeline for attendance'''
	return dict(frappe.db.sql('''select unix_timestamp(attendance_date), count(*)
		from `tabAttendance` where employee=%s
			and attendance_date > date_sub(curdate(), interval 1 year)
			and status in ('Present', 'Half Day')
			group by attendance_date''', name))

@frappe.whitelist()
def get_retirement_date(date_of_birth=None):
	ret = {}
	if date_of_birth:
		try:
			retirement_age = int(frappe.db.get_single_value("HR Settings", "retirement_age") or 60)
			dt = add_years(getdate(date_of_birth),retirement_age)
			ret = {'date_of_retirement': dt.strftime('%Y-%m-%d')}
		except ValueError:
			# invalid date
			ret = {}

	return ret

def validate_employee_role(doc, method):
	# called via User hook
	if "Employee" in [d.role for d in doc.get("roles")]:
		if not frappe.db.get_value("Employee", {"user_id": doc.name}):
			frappe.msgprint(_("Please set User ID field in an Employee record to set Employee Role"))
			doc.get("roles").remove(doc.get("roles", {"role": "Employee"})[0])

def update_user_permissions(doc, method):
	# called via User hook
	if "Employee" in [d.role for d in doc.get("roles")]:
		if not has_permission('User Permission', ptype='write', raise_exception=False): return
		employee = frappe.get_doc("Employee", {"user_id": doc.name})
		employee.update_user_permissions()

def send_birthday_reminders():
	"""Send Employee birthday reminders if no 'Stop Birthday Reminders' is not set."""
	if int(frappe.db.get_single_value("HR Settings", "stop_birthday_reminders") or 0):
		return

	birthdays = get_employees_who_are_born_today()

	if birthdays:
		employee_list = frappe.get_all('Employee',
			fields=['name','employee_name'],
			filters={'status': 'Active',
				'company': birthdays[0]['company']
		 	}
		)
		employee_emails = get_employee_emails(employee_list)
		birthday_names = [name["employee_name"] for name in birthdays]
		birthday_emails = [email["user_id"] or email["personal_email"] or email["company_email"] for email in birthdays]

		birthdays.append({'company_email': '','employee_name': '','personal_email': '','user_id': ''})

		for e in birthdays:
			if e['company_email'] or e['personal_email'] or e['user_id']:
				if len(birthday_names) == 1:
					continue
				recipients = e['company_email'] or e['personal_email'] or e['user_id']


			else:
				recipients = list(set(employee_emails) - set(birthday_emails))

			frappe.sendmail(recipients=recipients,
				subject=_("Birthday Reminder"),
				message=get_birthday_reminder_message(e, birthday_names),
				header=['Birthday Reminder', 'green'],
			)

def get_birthday_reminder_message(employee, employee_names):
	"""Get employee birthday reminder message"""
	pattern = "</Li><Br><Li>"
	message = pattern.join(filter(lambda u: u not in (employee['employee_name']), employee_names))
	message = message.title()

	if pattern not in message:
		message = "Today is {0}'s birthday \U0001F603".format(message)

	else:
		message = "Today your colleagues are celebrating their birthdays \U0001F382<br><ul><strong><li> " + message +"</li></strong></ul>"

	return message
def get_HR_Users():
    return frappe.db.sql_list("""
    		SELECT parent FROM `tabHas Role` WHERE `role` ='HR User' and `parenttype` = 'user' and parent <> 'Administrator'
    		""")


def get_employees_resident_data(resident_data_reminder):
    return frappe.db.sql_list("""select parent
		from `tabResident Data` where DATEDIFF(release_end_date,CURDATE() ) <= (%(day)s) and DATEDIFF(release_end_date,CURDATE() ) >= 0
		""", {"day": resident_data_reminder})


def get_employees_who_are_born_today():
	"""Get Employee properties whose birthday is today."""
	return frappe.db.get_values("Employee",
		fieldname=["name", "personal_email", "company", "company_email", "user_id", "employee_name"],
		filters={
			"date_of_birth": ("like", "%{}".format(format_datetime(getdate(), "-MM-dd"))),
			"status": "Active",
		},
		as_dict=True
	)


def get_holiday_list_for_employee(employee, raise_exception=True):
	if employee:
		holiday_list, company = frappe.db.get_value("Employee", employee, ["holiday_list", "company"])
	else:
		holiday_list=''
		company=frappe.db.get_value("Global Defaults", None, "default_company")

	if not holiday_list:
		holiday_list = frappe.get_cached_value('Company',  company,  "default_holiday_list")

	if not holiday_list and raise_exception:
		frappe.throw(_('Please set a default Holiday List for Employee {0} or Company {1}').format(employee, company))

	return holiday_list

def is_holiday(employee, date=None):
	'''Returns True if given Employee has an holiday on the given date
	:param employee: Employee `name`
	:param date: Date to check. Will check for today if None'''

	holiday_list = get_holiday_list_for_employee(employee)
	if not date:
		date = today()

	if holiday_list:
		return frappe.get_all('Holiday List', dict(name=holiday_list, holiday_date=date)) and True or False

@frappe.whitelist()
def deactivate_sales_person(status = None, employee = None):
	if status == "Left":
		sales_person = frappe.db.get_value("Sales Person", {"Employee": employee})
		if sales_person:
			frappe.db.set_value("Sales Person", sales_person, "enabled", 0)

@frappe.whitelist()
def create_user(employee, user = None, email=None):
	emp = frappe.get_doc("Employee", employee)

	employee_name = emp.employee_name.split(" ")
	middle_name = last_name = ""

	if len(employee_name) >= 3:
		last_name = " ".join(employee_name[2:])
		middle_name = employee_name[1]
	elif len(employee_name) == 2:
		last_name = employee_name[1]

	first_name = employee_name[0]

	if email:
		emp.prefered_email = email

	user = frappe.new_doc("User")
	user.update({
		"name": emp.employee_name,
		"email": emp.prefered_email,
		"enabled": 1,
		"first_name": first_name,
		"middle_name": middle_name,
		"last_name": last_name,
		"gender": emp.gender,
		"birth_date": emp.date_of_birth,
		"phone": emp.cell_number,
		"bio": emp.bio
	})
	user.insert()
	return user.name

@frappe.whitelist()
def create_position(designation, department):

    position = frappe.new_doc("Positions")
    position.update({
        "designation": designation,
        "department":  department
    })
    position.insert()
    return position.name


def get_employee_emails(employee_list):
	'''Returns list of employee emails either based on user_id or company_email'''
	employee_emails = []
	for employee in employee_list:
		if not employee:
			continue
		user, company_email, personal_email = frappe.db.get_value('Employee', employee,
											['user_id', 'company_email', 'personal_email'])
		email = user or company_email or personal_email
		if email:
			employee_emails.append(email)
	return employee_emails


@frappe.whitelist()
def get_unused_position(doctype, txt, searchfield, start, page_len, filters):
	from frappe.desk.reportview import get_match_cond, get_filters_cond
	conditions = []

	if not page_len:
		return frappe.db.sql("""
                select `name`
                    from tabPositions
                    where `status`='Active'
                    and name not in (select position  from tabEmployee where position is not NULL)
                    and ({key} like %(txt)s)
                    {fcond} {mcond}
                order by
                    if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999) desc """.format(**{
			'key': searchfield,
			'fcond': get_filters_cond(doctype, filters, conditions),
			'mcond': get_match_cond(doctype)
		}), {
								 'txt': "%%%s%%" % txt,
								 '_txt': txt.replace("%", ""),
							 })
	else:
		return frappe.db.sql("""
                select `name`
                    from tabPositions
                    where `status`='Active'
                    and name not in (select position  from tabEmployee where position is not NULL)
                    and ({key} like %(txt)s)
                    {fcond} {mcond}
                order by
                    if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999) desc

                limit %(start)s, %(page_len)s""".format(**{
			'key': searchfield,
			'fcond': get_filters_cond(doctype, filters, conditions),
			'mcond': get_match_cond(doctype)
		}), {
								 'txt': "%%%s%%" % txt,
								 '_txt': txt.replace("%", ""),
								 'start': start,
								 'page_len': page_len
							 })



@frappe.whitelist()
def get_children(doctype, parent=None, company=None, is_root=False, is_tree=False):
	filters = [['company', '=', company]]
	fields = ['name as value', 'employee_name as title']

	if is_root:
		parent = ''
	if parent and company and parent!=company:
		filters.append(['reports_to', '=', parent])
	else:
		filters.append(['reports_to', '=', ''])

	employees = frappe.get_list(doctype, fields=fields,
		filters=filters, order_by='name')

	for employee in employees:
		is_expandable = frappe.get_all(doctype, filters=[
			['reports_to', '=', employee.get('value')]
		])
		employee.expandable = 1 if is_expandable else 0

	return employees


@frappe.whitelist()
def get_retirement_date_for_gender(date_of_birth=None, gender=None):
    ret = {}
    if date_of_birth and gender:
        try:
            if gender == 'Male':
                retirement_age = int(frappe.db.get_single_value("HR Settings", "retirement_age_for_male") or 60)
            elif gender == 'Female':
                retirement_age = int(frappe.db.get_single_value("HR Settings", "retirement_age_for_female") or 55)
            dt = add_years(getdate(date_of_birth), retirement_age)
            ret = {'date_of_retirement': dt.strftime('%Y-%m-%d')}
        except ValueError:
            # invalid date
            ret = {}

    return ret

@frappe.whitelist()
def check_employee_min_age():
	min_age = 0
	try:
		min_age = int(frappe.db.get_single_value("HR Settings", "min_age_for_emp") or 18)
	except ValueError:
		pass

	return min_age

@frappe.whitelist()
def get_test_period_end_date(date_of_joining=None):
    ret = {}
    if date_of_joining:
        try:
            test_days = int(frappe.db.get_single_value("HR Settings", "test_period") or 90)
            dt = add_days(getdate(date_of_joining), test_days)
            ret = {'test_period_end_date': dt.strftime('%Y-%m-%d')}
        except ValueError:
            # invalid date
            ret = {}

    return ret

def on_doctype_update():
	frappe.db.add_index("Employee", ["lft", "rgt"])

def has_user_permission_for_employee(user_name, employee_name):
	return frappe.db.exists({
		'doctype': 'User Permission',
		'user': user_name,
		'allow': 'Employee',
		'for_value': employee_name
	})
