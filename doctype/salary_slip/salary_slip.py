# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe, erpnext
import datetime, math
from frappe.utils import add_days, cint, cstr, flt, getdate, rounded, date_diff, money_in_words
from frappe.model.naming import make_autoname
from frappe import msgprint, _
from collections import Counter
from erpnext.hr.doctype.payroll_entry.payroll_entry import get_start_end_dates
from erpnext.hr.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.utilities.transaction_base import TransactionBase
from frappe.utils.background_jobs import enqueue
from erpnext.hr.doctype.additional_salary.additional_salary import get_additional_salary_component
from erpnext.hr.doctype.payroll_period.payroll_period import get_period_factor, get_payroll_period
from erpnext.hr.doctype.employee_benefit_application.employee_benefit_application import get_benefit_component_amount
from erpnext.hr.doctype.employee_benefit_claim.employee_benefit_claim import get_benefit_claim_amount, get_last_payroll_period_benefits
from erpnext.utils.utils import Overlab_Dates, get_month_days,get_over_time_hour_range,get_daily_work_hours

class SalarySlip(TransactionBase):
	def __init__(self, *args, **kwargs):
		super(SalarySlip, self).__init__(*args, **kwargs)
		self.series = 'Sal Slip/{0}/.#####'.format(self.employee)
		self.whitelisted_globals = {
			"int": int,
			"float": float,
			"long": int,
			"round": round,
			"date": datetime.date,
			"getdate": getdate
		}

	def autoname(self):
		self.name = make_autoname(self.series)

	def validate(self):
		self.status = self.get_status()
		self.validate_dates()
		self.check_existing()
		if not self.salary_slip_based_on_timesheet:
			self.get_date_details()

		if not (len(self.get("earnings")) or len(self.get("deductions"))):
			# get details from salary structure
			self.get_emp_and_leave_details()
		else:
			self.get_leave_details(lwp = self.leave_without_pay)

		self.calculate_net_pay()

		company_currency = erpnext.get_company_currency(self.company)
		self.total_in_words = money_in_words(self.rounded_total, company_currency)

		if frappe.db.get_single_value("HR Settings", "max_working_hours_against_timesheet"):
			max_working_hours = frappe.db.get_single_value("HR Settings", "max_working_hours_against_timesheet")
			if self.salary_slip_based_on_timesheet and (self.total_working_hours > int(max_working_hours)):
				frappe.msgprint(_("Total working hours should not be greater than max working hours {0}").
								format(max_working_hours), alert=True)

	def on_submit(self):
		if self.net_pay < 0:
			frappe.throw(_("Net Pay cannot be less than 0"))
		else:
			self.set_status()
			self.update_status(self.name)
			self.update_salary_slip_in_additional_salary()
			if (frappe.db.get_single_value("HR Settings", "email_salary_slip_to_employee")) and not frappe.flags.via_payroll_entry:
				self.email_salary_slip()

	def on_cancel(self):
		self.set_status()
		self.update_status()
		self.update_salary_slip_in_additional_salary()

	def on_trash(self):
		from frappe.model.naming import revert_series_if_last
		revert_series_if_last(self.series, self.name)

	def ValidateDamages(self, data):
		MonthDays = get_month_days(self.start_date)

		self.damagesAmount = 0.0
		for item in data["deductions"]:
			if item["salary_component"] == "Damages":
				self.damagesAmount += float(item["amount"])

		if self.damagesAmount > 0:
			if (self.damagesAmount > ((float(data["gross_pay"]) / MonthDays) * 5)):
				frappe.throw(_("Sorry....Damage total should not be more than five days of month salary") + " (" + str(
					((float(data["gross_pay"]) / MonthDays) * 5)) + ")")

	def Check_Stop_Working(self, Start_Date, End_Date, Employee):
		MonthDays = get_month_days(self.start_date)
		Stop_working_Percentage = 0.0

		Stop_Working_Dict = frappe.db.sql((
			""" 
			SELECT cut_percentage,start_date,end_date
				from `tabStop Working Data`
					where parent =%(Employee)s	
						and docstatus='0'
						and (
						%(Start_Date)s  BETWEEN start_date and end_date or %(End_Date)s  BETWEEN start_date and end_date
						or (%(Start_Date)s   >= start_date and %(End_Date)s  <= end_date)
						or (start_date BETWEEN %(Start_Date)s  and %(End_Date)s )
						or (end_date BETWEEN %(Start_Date)s  and %(End_Date)s )
						or %(End_Date)s   <= end_date				
						)
			"""
		), ({'Employee': Employee, "Start_Date": Start_Date, "End_Date": End_Date}),
			as_dict=1)

		if Stop_Working_Dict:
			Stop_Working_Dict = Stop_Working_Dict[0]
			cut_percentage = Stop_Working_Dict["cut_percentage"]
			start_date = Stop_Working_Dict["start_date"]
			end_date = Stop_Working_Dict["end_date"]

			Stop_working_Days = Overlab_Dates(str(start_date), str(end_date), str(Start_Date), str(End_Date))

			if Stop_working_Days > MonthDays:
				Stop_working_Days = MonthDays

			if Stop_working_Days > 0:
				Stop_working_Percentage = float(float(Stop_working_Days) / MonthDays) * float(
					float(cut_percentage) / 100) + float(MonthDays - Stop_working_Days) / MonthDays

		return Stop_working_Percentage

	def check_treatment_per(self, Start_Date, End_Date, Employee):
		MonthDays = get_month_days(self.start_date)
		treatment_percentage = 1.0

		treatment_dict = frappe.db.sql((
			""" 
			SELECT treatment_start_date,treatment_end_date,injury_type
				from `tabWork Injury`
					where parent =%(Employee)s	
						and docstatus='0'
						and (
						%(Start_Date)s  BETWEEN treatment_start_date and treatment_end_date or %(End_Date)s  BETWEEN treatment_start_date and treatment_end_date
						or (%(Start_Date)s   >= treatment_start_date and %(End_Date)s  <= treatment_end_date)
						or (treatment_start_date BETWEEN %(Start_Date)s  and %(End_Date)s )
						or (treatment_end_date BETWEEN %(Start_Date)s  and %(End_Date)s )
						or %(End_Date)s   <= treatment_end_date				
						)
			"""
		), ({'Employee': Employee, "Start_Date": Start_Date, "End_Date": End_Date}),
			as_dict=1)
		if treatment_dict:
			treatment_dict = treatment_dict[0]
			treatment_start_date = treatment_dict["treatment_start_date"]
			treatment_end_date = treatment_dict["treatment_end_date"]
			injury_type = treatment_dict["injury_type"]
			discount_percentage = frappe.db.get_value("Injury Type", injury_type, "discount_percentage")
			treatment_days = Overlab_Dates(str(treatment_start_date), str(treatment_end_date), str(Start_Date),
										   str(End_Date))
			cut_percentage = discount_percentage
			if treatment_days > MonthDays:
				treatment_days = MonthDays

			if treatment_days > 0:
				treatment_percentage = float(float(treatment_days) / MonthDays) * float(
					float(cut_percentage) / 100) + float(MonthDays - treatment_days) / MonthDays

		return treatment_percentage

	def get_status(self):
		if self.docstatus == 0:
			status = "Draft"
		elif self.docstatus == 1:
			status = "Submitted"
		elif self.docstatus == 2:
			status = "Cancelled"
		return status

	def validate_dates(self):
		if date_diff(self.end_date, self.start_date) < 0:
			frappe.throw(_("To date cannot be before From date"))

	def check_existing(self):
		if not self.salary_slip_based_on_timesheet:
			ret_exist = frappe.db.sql("""select name from `tabSalary Slip`
						where start_date = %s and end_date = %s and docstatus != 2
						and employee = %s and name != %s""",
									  (self.start_date, self.end_date, self.employee, self.name))
			if ret_exist:
				self.employee = ''
				frappe.throw(_("Salary Slip of employee {0} already created for this period").format(self.employee))
		else:
			for data in self.timesheets:
				if frappe.db.get_value('Timesheet', data.time_sheet, 'status') == 'Payrolled':
					frappe.throw(_("Salary Slip of employee {0} already created for time sheet {1}").format(self.employee, data.time_sheet))

	def get_date_details(self):
		if not self.end_date:
			date_details = get_start_end_dates(self.payroll_frequency, self.start_date or self.posting_date)
			self.start_date = date_details.start_date
			self.end_date = date_details.end_date

	def get_emp_and_leave_details(self):
		'''First time, load all the components from salary structure'''
		if self.employee:
			self.set("earnings", [])
			self.set("deductions", [])
			self.set("insurance", [])

			if not self.salary_slip_based_on_timesheet:
				self.get_date_details()
			self.validate_dates()
			joining_date, relieving_date = frappe.get_cached_value("Employee", self.employee,
																   ["date_of_joining", "relieving_date"])

			self.get_leave_details(joining_date, relieving_date)
			struct = self.check_sal_struct(joining_date, relieving_date)

			if struct:
				self._salary_structure_doc = frappe.get_doc('Salary Structure', struct)
				self.salary_slip_based_on_timesheet = self._salary_structure_doc.salary_slip_based_on_timesheet or 0
				self.set_time_sheet()
				self.pull_sal_struct()

	def set_time_sheet(self):
		if self.salary_slip_based_on_timesheet:
			self.set("timesheets", [])
			timesheets = frappe.db.sql(""" select * from `tabTimesheet` where employee = %(employee)s and start_date BETWEEN %(start_date)s AND %(end_date)s and (status = 'Submitted' or
				status = 'Billed')""", {'employee': self.employee, 'start_date': self.start_date, 'end_date': self.end_date}, as_dict=1)

			for data in timesheets:
				self.append('timesheets', {
					'time_sheet': data.name,
					'working_hours': data.total_hours
				})

	def check_sal_struct(self, joining_date, relieving_date):
		cond = """and sa.employee=%(employee)s and (sa.from_date <= %(start_date)s or
				sa.from_date <= %(end_date)s or sa.from_date <= %(joining_date)s)"""
		if self.payroll_frequency:
			cond += """and ss.payroll_frequency = '%(payroll_frequency)s'""" % {"payroll_frequency": self.payroll_frequency}

		st_name = frappe.db.sql("""
			select sa.salary_structure
			from `tabSalary Structure Assignment` sa join `tabSalary Structure` ss
			where sa.salary_structure=ss.name
				and sa.docstatus = 1 and ss.docstatus = 1 and ss.is_active ='Yes' %s
			order by sa.from_date desc
			limit 1
		""" %cond, {'employee': self.employee, 'start_date': self.start_date,
					'end_date': self.end_date, 'joining_date': joining_date})

		if st_name:
			self.salary_structure = st_name[0][0]
			return self.salary_structure

		else:
			self.salary_structure = None
			frappe.msgprint(_("No active or default Salary Structure found for employee {0} for the given dates")
							.format(self.employee), title=_('Salary Structure Missing'))

	def pull_sal_struct(self):
		from erpnext.hr.doctype.salary_structure.salary_structure import make_salary_slip

		if self.salary_slip_based_on_timesheet:
			self.salary_structure = self._salary_structure_doc.name
			self.hour_rate = self._salary_structure_doc.hour_rate
			self.total_working_hours = sum([d.working_hours or 0.0 for d in self.timesheets]) or 0.0
			wages_amount = self.hour_rate * self.total_working_hours

			self.add_earning_for_hourly_wages(self, self._salary_structure_doc.salary_component, wages_amount)

		make_salary_slip(self._salary_structure_doc.name, self)

	def get_leave_details(self, joining_date=None, relieving_date=None, lwp=None, for_preview=0):
		MonthDays = get_month_days(self.start_date)
		if not joining_date:
			joining_date, relieving_date = frappe.get_cached_value("Employee", self.employee,
																   ["date_of_joining", "relieving_date"])

		working_days = date_diff(self.end_date, self.start_date) + 1
		if working_days > MonthDays:
			working_days = MonthDays

		if for_preview:
			self.total_working_days = working_days
			self.payment_days = working_days
			return

		holidays = self.get_holidays_for_employee(self.start_date, self.end_date)
		self.holidays = len(holidays)

		actual_lwp = self.calculate_lwp(holidays, working_days)
		leave_lwpp = self.calculate_lwpp(holidays, working_days)

		actual_lwp += leave_lwpp

		if not cint(frappe.db.get_value("HR Settings", None, "include_holidays_in_total_working_days")):
			# working_days -= len(holidays)
			if working_days < 0:
				frappe.throw(_("There are more holidays than working days this month."))

		if not lwp:
			lwp = actual_lwp
		elif lwp != actual_lwp:
			frappe.msgprint(_("Leave Without Pay does not match with approved Leave Application records"))

		self.total_working_days = working_days
		self.leave_without_pay = lwp
		payment_days = flt(self.get_payment_days(joining_date, relieving_date)) - flt(lwp)
		self.payment_days = payment_days > 0 and payment_days or 0

	def get_payment_days(self, joining_date, relieving_date):
		MonthDays = get_month_days(self.start_date)
		start_date = getdate(self.start_date)
		if joining_date:
			if getdate(self.start_date) <= joining_date <= getdate(self.end_date):
				start_date = joining_date
			elif joining_date > getdate(self.end_date):
				return

		end_date = getdate(self.end_date)
		if relieving_date:
			if getdate(self.start_date) <= relieving_date <= getdate(self.end_date):
				end_date = relieving_date
			elif relieving_date < getdate(self.start_date):
				frappe.throw(_("Employee relieved on {0} must be set as 'Left'")
							 .format(relieving_date))

		payment_days = date_diff(end_date, start_date) + 1
		if payment_days > MonthDays:
			payment_days = MonthDays

		if not cint(frappe.db.get_value("HR Settings", None, "include_holidays_in_total_working_days")):
			holidays = self.get_holidays_for_employee(start_date, end_date)
			payment_days -= len(holidays)
		return payment_days

	def get_holidays_for_employee(self, start_date, end_date):
		holiday_list = get_holiday_list_for_employee(self.employee)
		holidays = frappe.db.sql_list('''select holiday_date from `tabHoliday`
			where
				parent=%(holiday_list)s
				and holiday_date >= %(start_date)s
				and holiday_date <= %(end_date)s''', {
			"holiday_list": holiday_list,
			"start_date": start_date,
			"end_date": end_date
		})

		holidays = [cstr(i) for i in holidays]

		return holidays

	def calculate_lwp(self, holidays, working_days):
		lwp = 0
		holidays = "','".join(holidays)
		for d in range(working_days):
			dt = add_days(cstr(getdate(self.start_date)), d)
			leave = frappe.db.sql("""
				select t1.name, t1.half_day
				from `tabLeave Application` t1, `tabLeave Type` t2
				where t2.name = t1.leave_type
				and t2.is_lwp = 1
				and t1.docstatus = 1
				and t1.employee = %(employee)s
				and CASE WHEN t2.include_holiday != 1 THEN %(dt)s not in ('{0}') and %(dt)s between from_date and to_date and ifnull(t1.salary_slip, '') = ''
				WHEN t2.include_holiday THEN %(dt)s between from_date and to_date and ifnull(t1.salary_slip, '') = ''
				END
				""".format(holidays), {"employee": self.employee, "dt": dt})
			if leave:
				lwp = cint(leave[0][1]) and (lwp + 0.5) or (lwp + 1)
		return lwp

	def calculate_lwpp(self, holidays, working_days):
		return  0
		lwpp = 0.0
		holidays = "','".join(holidays)
		for d in range(working_days):
			dt = add_days(cstr(getdate(self.start_date)), d)
			leave = frappe.db.sql("""
					select t1.name, t1.half_day, 1 - (t2.payroll_ratio / 100) payroll_ratio
					from `tabLeave Application` t1, `tabLeave Type` t2
					where t2.name = t1.leave_type
					and t2.vacation_type='Sick Vacation'
					and t1.docstatus = 1
					and t1.status = 'Approved'
					and t1.employee = %(employee)s
					and CASE WHEN t2.include_holiday != 1 THEN %(dt)s not in ('{0}') and %(dt)s between from_date and to_date
					WHEN t2.include_holiday THEN %(dt)s between from_date and to_date
					END
					""".format(holidays), {"employee": self.employee, "dt": dt})
			if leave:
				lwpp = (cint(leave[0][1]) and (lwpp + 0.5)) or (flt(leave[0][2]) and (lwpp + flt(leave[0][2]))) or (
						lwpp + 1)

		return lwpp

	def add_earning_for_hourly_wages(self, doc, salary_component, amount):
		row_exists = False
		for row in doc.earnings:
			if row.salary_component == salary_component:
				row.amount = amount
				row_exists = True
				break

		if not row_exists:
			wages_row = {
				"salary_component": salary_component,
				"abbr": frappe.db.get_value("Salary Component", salary_component, "salary_component_abbr"),
				"amount": self.hour_rate * self.total_working_hours,
				"default_amount": 0.0,
				"additional_amount": 0.0
			}
			doc.append('earnings', wages_row)

	def calculate_net_pay(self):
		if self.salary_structure:
			self.calculate_component_amounts()

		self.gross_pay = self.get_component_totals("earnings")
		self.total_deduction = self.get_component_totals("deductions")
		self.sum_components('insurance', 'total_deduction')

		self.set_loan_repayment()

		self.net_pay = flt(self.gross_pay) - (flt(self.total_deduction) + flt(self.total_loan_repayment))
		self.rounded_total = rounded(self.net_pay)

	def calculate_component_amounts(self):
		if not getattr(self, '_salary_structure_doc', None):
			self._salary_structure_doc = frappe.get_doc('Salary Structure', self.salary_structure)

		payroll_period = get_payroll_period(self.start_date, self.end_date, self.company)

		self.add_structure_components()
		self.add_employee_benefits(payroll_period)
		self.add_additional_salary_components()
		self.add_tax_components(payroll_period)
		self.set_component_amounts_based_on_payment_days()

	def add_structure_components(self):
		data = self.get_data_for_eval()

		Stop_working_Percentage = self.Check_Stop_Working(self.start_date, self.end_date, self.employee)
		Stop_working_Percentage = (Stop_working_Percentage if Stop_working_Percentage != 0.0 else 0.0)
		treatment_percentage = self.check_treatment_per(self.start_date, self.end_date, self.employee)
		treatment_percentage = (treatment_percentage if treatment_percentage else 1.0)

		for key in ('earnings', 'deductions', 'insurance'):
			for struct_row in self._salary_structure_doc.get(key):
				amount = self.eval_condition_and_formula(struct_row, data)
				if key == 'earnings':
					Stop_working_amount = (amount * Stop_working_Percentage)
					amount = amount - Stop_working_amount
					if not struct_row.abbr == 'IN':
						amount = (amount * treatment_percentage)

				if amount and struct_row.statistical_component == 0:
					self.update_component_row(struct_row, amount, key)

	def get_data_for_eval(self):
		'''Returns data for evaluating formula'''
		data = frappe._dict()

		data.update(frappe.get_doc("Salary Structure Assignment",
								   {"employee": self.employee, "salary_structure": self.salary_structure}).as_dict())

		data.update(frappe.get_doc("Employee", self.employee).as_dict())
		data.update(self.as_dict())

		# set values for components
		salary_components = frappe.get_all("Salary Component", fields=["salary_component_abbr"])
		for sc in salary_components:
			data.setdefault(sc.salary_component_abbr, 0)

		for key in ('earnings', 'deductions', 'insurance'):
			for d in self.get(key):
				data[d.abbr] = d.amount

		return data

	def eval_condition_and_formula(self, d, data):
		amount_based_on_func = 0.0
		# try:
		condition = d.condition.strip() if d.condition else None
		if condition:
			if not frappe.safe_eval(condition, self.whitelisted_globals, data):
				return None

		if d.amount_based_on_func:
			if d.salary_component in ["Penalties"]:
				d.amount = self.calculate_penalty(data, d)

			if d.salary_component in ["Indemnity"]:
				d.amount = self.calculate_indemnity(data, d)

			if d.abbr=="AB":
				amount_based_on_func = self.calculate_absence_days(data, d)
				# msgprint(str(amount_based_on_func))
			if d.abbr=="OVRTM":
				amount_based_on_func = self.calculate_overtime(data, d)
			if d.abbr=="DELAYCut":
				amount_based_on_func = self.calculate_delay_minutes(data, d)

		amount = d.amount
		if d.amount_based_on_formula:
			formula = d.formula.strip() if d.formula else None
			# msgprint(str(d.salary_component)+"============formula====="+str(formula))
			if formula:
				amount = flt(frappe.safe_eval(formula, self.whitelisted_globals, data), d.precision("amount"))
				if d.abbr in ("AB","OVRTM","DELAYCut"):
					amount = amount_based_on_func * amount


		if amount:
			data[d.abbr] = amount

		return amount

		# except NameError as err:
		# 	frappe.throw(_("Name error: {0}".format(err)))
		# except SyntaxError as err:
		# 	frappe.throw(_("Syntax error in formula or condition: {0}".format(err)))
		# except Exception as e:
		# 	frappe.throw(_("Error in formula or condition: {0}".format(e)))
		# 	raise
	def calculate_delay_minutes (self,data,d):
		MonthDays = get_month_days(self.start_date)
		daily_work_hours = get_daily_work_hours()
		# get delay minutes from time attendance
		# total_minutes = self.get_dela_mintues(self.employee,self.start_date)
		total_minutes = 480
		amount_per_minute = flt(total_minutes) / (flt(daily_work_hours) * 60) / flt(MonthDays)

		return amount_per_minute

	def calculate_overtime(self,data, d):
		MonthDays = get_month_days(self.start_date)
		# get over time from time attendance
		# total_minutes = self.get_over_time(self.employee,self.start_date)
		total_minitues = 180
		over_time_hour_range = get_over_time_hour_range()
		daily_work_hours = get_daily_work_hours()
		total_minitues = flt(total_minitues) * flt(over_time_hour_range)
		amount_per_minute = total_minitues / MonthDays/daily_work_hours/60

		return amount_per_minute

	def calculate_absence_days(self,data, d):
		MonthDays = get_month_days(self.start_date)
		# get absence from time attendance
		# total_absence_days = self.absence_days(self.employee,self.start_date)
		total_absence_days = 3
		amount_for_absence =  flt(total_absence_days) / flt(MonthDays)
		return amount_for_absence

	def add_employee_benefits(self, payroll_period):
		for struct_row in self._salary_structure_doc.get("earnings"):
			if struct_row.is_flexible_benefit == 1:
				if frappe.db.get_value("Salary Component", struct_row.salary_component, "pay_against_benefit_claim") != 1:
					benefit_component_amount = get_benefit_component_amount(self.employee, self.start_date, self.end_date,
																			struct_row.salary_component, self._salary_structure_doc, self.payroll_frequency, payroll_period)
					if benefit_component_amount:
						self.update_component_row(struct_row, benefit_component_amount, "earnings")
				else:
					benefit_claim_amount = get_benefit_claim_amount(self.employee, self.start_date, self.end_date, struct_row.salary_component)
					if benefit_claim_amount:
						self.update_component_row(struct_row, benefit_claim_amount, "earnings")

		self.adjust_benefits_in_last_payroll_period(payroll_period)

	def adjust_benefits_in_last_payroll_period(self, payroll_period):
		if payroll_period:
			if (getdate(payroll_period.end_date) <= getdate(self.end_date)):
				last_benefits = get_last_payroll_period_benefits(self.employee, self.start_date, self.end_date,
																 payroll_period, self._salary_structure_doc)
				if last_benefits:
					for last_benefit in last_benefits:
						last_benefit = frappe._dict(last_benefit)
						amount = last_benefit.amount
						self.update_component_row(frappe._dict(last_benefit.struct_row), amount, "earnings")

	def add_additional_salary_components(self):
		additional_components = get_additional_salary_component(self.employee, self.start_date, self.end_date)
		if additional_components:
			for additional_component in additional_components:
				amount = additional_component.amount
				overwrite = additional_component.overwrite
				key = "earnings" if additional_component.type == "Earning" else "deductions"
				self.update_component_row(frappe._dict(additional_component.struct_row), amount, key, overwrite=overwrite)

	def add_tax_components(self, payroll_period):
		# Calculate variable_based_on_taxable_salary after all components updated in salary slip
		tax_components, other_deduction_components = [], []
		for d in self._salary_structure_doc.get("deductions"):
			if d.variable_based_on_taxable_salary == 1 and not d.formula and not flt(d.amount):
				tax_components.append(d.salary_component)
			else:
				other_deduction_components.append(d.salary_component)

		if not tax_components:
			tax_components = [d.name for d in frappe.get_all("Salary Component", filters={"variable_based_on_taxable_salary": 1})
							  if d.name not in other_deduction_components]

		for d in tax_components:
			tax_amount = self.calculate_variable_based_on_taxable_salary(d, payroll_period)
			tax_row = self.get_salary_slip_row(d)
			self.update_component_row(tax_row, tax_amount, "deductions")

	def update_component_row(self, struct_row, amount, key, overwrite=1):
		component_row = None
		for d in self.get(key):
			if d.salary_component == struct_row.salary_component:
				component_row = d

		if not component_row:
			if amount:
				self.append(key, {
					'amount': amount,
					'default_amount': amount if not struct_row.get("is_additional_component") else 0,
					'depends_on_payment_days' : struct_row.depends_on_payment_days,
					'salary_component' : struct_row.salary_component,
					'abbr' : struct_row.abbr,
					'do_not_include_in_total' : struct_row.do_not_include_in_total,
					'is_tax_applicable': struct_row.is_tax_applicable,
					'is_flexible_benefit': struct_row.is_flexible_benefit,
					'depends_on_lwp': struct_row.depends_on_lwp,
					'variable_based_on_taxable_salary': struct_row.variable_based_on_taxable_salary,
					'deduct_full_tax_on_selected_payroll_date': struct_row.deduct_full_tax_on_selected_payroll_date,
					'additional_amount': amount if struct_row.get("is_additional_component") else 0
				})
		else:
			if struct_row.get("is_additional_component"):
				if overwrite:
					component_row.additional_amount = amount - component_row.get("default_amount", 0)
				else:
					component_row.additional_amount = amount

				if not overwrite and component_row.default_amount:
					amount += component_row.default_amount
			else:
				component_row.default_amount = amount

			component_row.amount = amount
			component_row.deduct_full_tax_on_selected_payroll_date = struct_row.deduct_full_tax_on_selected_payroll_date

	def calculate_variable_based_on_taxable_salary(self, tax_component, payroll_period):
		if not payroll_period:
			frappe.msgprint(_("Start and end dates not in a valid Payroll Period, cannot calculate {0}.")
							.format(tax_component))
			return

		# Deduct taxes forcefully for unsubmitted tax exemption proof and unclaimed benefits in the last period
		if payroll_period.end_date <= getdate(self.end_date):
			self.deduct_tax_for_unsubmitted_tax_exemption_proof = 1
			self.deduct_tax_for_unclaimed_employee_benefits = 1

		return self.calculate_variable_tax(payroll_period, tax_component)

	def calculate_variable_tax(self, payroll_period, tax_component):
		# get remaining numbers of sub-period (period for which one salary is processed)
		remaining_sub_periods = get_period_factor(self.employee,
												  self.start_date, self.end_date, self.payroll_frequency, payroll_period)[1]

		# get taxable_earnings, paid_taxes for previous period
		previous_taxable_earnings = self.get_taxable_earnings_for_prev_period(payroll_period.start_date, self.start_date)
		previous_total_paid_taxes = self.get_tax_paid_in_period(payroll_period.start_date, self.start_date, tax_component)

		# get taxable_earnings for current period (all days)
		current_taxable_earnings = self.get_taxable_earnings()
		future_structured_taxable_earnings = current_taxable_earnings.taxable_earnings * (math.ceil(remaining_sub_periods) - 1)

		# get taxable_earnings, addition_earnings for current actual payment days
		current_taxable_earnings_for_payment_days = self.get_taxable_earnings(based_on_payment_days=1)
		current_structured_taxable_earnings = current_taxable_earnings_for_payment_days.taxable_earnings
		current_additional_earnings = current_taxable_earnings_for_payment_days.additional_income
		current_additional_earnings_with_full_tax = current_taxable_earnings_for_payment_days.additional_income_with_full_tax

		# Get taxable unclaimed benefits
		unclaimed_taxable_benefits = 0
		if self.deduct_tax_for_unclaimed_employee_benefits:
			unclaimed_taxable_benefits = self.calculate_unclaimed_taxable_benefits(payroll_period)
			unclaimed_taxable_benefits += current_taxable_earnings_for_payment_days.flexi_benefits

		# Total exemption amount based on tax exemption declaration
		total_exemption_amount, other_incomes = self.get_total_exemption_amount_and_other_incomes(payroll_period)

		# Total taxable earnings including additional and other incomes
		total_taxable_earnings = previous_taxable_earnings + current_structured_taxable_earnings + future_structured_taxable_earnings \
								 + current_additional_earnings + other_incomes + unclaimed_taxable_benefits - total_exemption_amount

		# Total taxable earnings without additional earnings with full tax
		total_taxable_earnings_without_full_tax_addl_components = total_taxable_earnings - current_additional_earnings_with_full_tax

		# Structured tax amount
		total_structured_tax_amount = self.calculate_tax_by_tax_slab(payroll_period, total_taxable_earnings_without_full_tax_addl_components)
		current_structured_tax_amount = (total_structured_tax_amount - previous_total_paid_taxes) / remaining_sub_periods

		# Total taxable earnings with additional earnings with full tax
		full_tax_on_additional_earnings = 0.0
		if current_additional_earnings_with_full_tax:
			total_tax_amount = self.calculate_tax_by_tax_slab(payroll_period, total_taxable_earnings)
			full_tax_on_additional_earnings = total_tax_amount - total_structured_tax_amount

		current_tax_amount = current_structured_tax_amount + full_tax_on_additional_earnings
		if flt(current_tax_amount) < 0:
			current_tax_amount = 0

		return current_tax_amount

	def calculate_indemnity(self, data, d):

		current_gross_pay = self.calculate_gross_pay(data)

		if data['employee_work_injuries']:
			for work_injuriy in data['employee_work_injuries']:
				if getdate(data['start_date']) <= work_injuriy.injury_date <= getdate(data['end_date']):
					with_indemnity = frappe.db.get_value("Injury Type", work_injuriy.injury_type, "with_indemnity")
					if with_indemnity:
						indemnity_days_for_work_injuries = int(
							frappe.db.get_single_value('HR Settings', 'indemnity_days_for_work_injuries') or 60)
						if data['IN']:
							d.amount = ((current_gross_pay - float(
								data['IN'])) / 30.0) * indemnity_days_for_work_injuries
						else:
							d.amount = (current_gross_pay / 30.0) * indemnity_days_for_work_injuries

		else:
			d.amount = 0

		return d.amount

	def sum_components(self, component_type, total_field):
		joining_date, relieving_date = frappe.db.get_value("Employee", self.employee,
														   ["date_of_joining", "relieving_date"])

		if not relieving_date:
			relieving_date = getdate(self.end_date)

		if not joining_date:
			frappe.throw(_("Please set the Date Of Joining for employee {0}").format(
				frappe.bold(self.employee_name)))

		for d in self.get(component_type):
			if (self.salary_structure and
					cint(d.depends_on_lwp) and
					(not
					 self.salary_slip_based_on_timesheet or
					 getdate(self.start_date) < joining_date or
					 getdate(self.end_date) > relieving_date
					)):

				d.amount = rounded(
					(flt(d.default_amount) * flt(self.payment_days)
					 / cint(self.total_working_days)), self.precision("amount", component_type)
				)

			elif not self.payment_days and not self.salary_slip_based_on_timesheet and \
					cint(d.depends_on_lwp):
				d.amount = 0

			elif not d.amount:
				d.amount = d.default_amount

			if not d.do_not_include_in_total:
				self.set(total_field, self.get(total_field) + flt(d.amount))
		# msgprint(cstr(self.total_deduction))

	def get_taxable_earnings_for_prev_period(self, start_date, end_date):

		taxable_earnings = frappe.db.sql("""
			select sum(sd.amount)
			from
				`tabSalary Detail` sd join `tabSalary Slip` ss on sd.parent=ss.name
			where
				sd.parentfield='earnings'
				and sd.is_tax_applicable=1
				and is_flexible_benefit=0
				and ss.docstatus=1
				and ss.employee=%(employee)s
				and ss.start_date between %(from_date)s and %(to_date)s
				and ss.end_date between %(from_date)s and %(to_date)s
			""", {
			"employee": self.employee,
			"from_date": start_date,
			"to_date": end_date
		})
		return flt(taxable_earnings[0][0]) if taxable_earnings else 0

	def get_tax_paid_in_period(self, start_date, end_date, tax_component):
		# find total_tax_paid, tax paid for benefit, additional_salary
		total_tax_paid = flt(frappe.db.sql("""
			select
				sum(sd.amount)
			from
				`tabSalary Detail` sd join `tabSalary Slip` ss on sd.parent=ss.name
			where
				sd.parentfield='deductions'
				and sd.salary_component=%(salary_component)s
				and sd.variable_based_on_taxable_salary=1
				and ss.docstatus=1
				and ss.employee=%(employee)s
				and ss.start_date between %(from_date)s and %(to_date)s
				and ss.end_date between %(from_date)s and %(to_date)s
		""", {
			"salary_component": tax_component,
			"employee": self.employee,
			"from_date": start_date,
			"to_date": end_date
		})[0][0])

		return total_tax_paid

	def get_penalty_rule(self,penalty, apply_date, times):
		formula = ""
		Penalty_Dict = frappe.db.sql((
			"""
			   select PS.penalty_type,PS.from_date,PS.to_date,
			   PD.times, PD.deduct_value,PD.deduct_value_type,PD.deduct_value_of,
			   (select salary_component_abbr from `tabSalary Component` where salary_component=PD.deduct_value_of)  abbr
				from `tabPenalties Settings` PS
					 INNER JOIN `tabPenalties Data` PD
					   on PS.name = PD.parent
					   and PS.penalty_type = %(penalty)s
					   and  %(apply_date)s  BETWEEN PS.from_date AND ifnull(PS.to_date,now())
					   and times = %(times)s
					   order by PS.penalty_type, PD.times;
			 """
		), ({'apply_date': apply_date, "penalty": penalty, "times": times}),
			as_dict=True)

		if Penalty_Dict:
			Penalty_Dict = Penalty_Dict[0]
			deduct_value = Penalty_Dict["deduct_value"]
			deduct_value_type = Penalty_Dict["deduct_value_type"]
			abbr = Penalty_Dict["abbr"]
			if (deduct_value_type == "Days"):
				formula = "( " + str(abbr) + "/30) *  " + \
						  str(float(deduct_value)) + " "
			elif (deduct_value_type == "Percentage"):
				formula = "(" + str(float(deduct_value)) + \
						  " / 100) * " + str(abbr) + " "
			elif (deduct_value_type == "Amount"):
				formula = deduct_value
		# frappe.msgprint(str(formula))
		return formula

	def pre_penalty_amount(self,penalty_list, CountItems, data, mounth_pen_list):
		penalty_set = []
		penalty_amount = 0
		for emp_penalty in penalty_list:
			if emp_penalty["penaltytype"] in mounth_pen_list:
				if emp_penalty["penaltytype"] not in penalty_set:
					penalty_set.append(emp_penalty["penaltytype"])
					rule_dict = self.get_penalty_rule(emp_penalty["penaltytype"], emp_penalty['apply_date'],
												 CountItems[emp_penalty["penaltytype"]])

					formula = rule_dict.strip() if rule_dict else None
					if formula:
						penalty_amount += frappe.safe_eval(formula, None, data)

		return penalty_amount

	def calculate_penalty(self, data, d):
		penalty_list, month_penalty_list = [], []
		mounth_penalty, penalty_amount, calc_using_pre = 0, 0, False
		if data['employee_penalties']:
			# msgprint(str(data['employee_penalties']))
			for penalty in data['employee_penalties']:
				if data['end_date']:
					if not data['start_date']:
						data['start_date'] = data['end_date'].replace(
							data['end_date'].split('-')[-1], '1')
					# msgprint("penalty.penalty_type====="+str(penalty.penalty_type))
					rule_start_date = frappe.db.get_value("Penalties Settings", {"penalty_type": penalty.penalty_type},"from_date")
					rule_end_date = frappe.db.get_value("Penalties Settings", {"penalty_type": penalty.penalty_type},"to_date")
					# frappe.msgprint(str(rule_end_date)+"===========>" + str(rule_start_date))
					if getdate(rule_start_date) <= penalty.apply_date <= getdate(rule_end_date):
						if penalty.apply_date < getdate(data['end_date']):
							penalty_list.append({"penaltytype": penalty.penalty_type, "apply_date": penalty.apply_date})
						if getdate(data['start_date']) <= penalty.apply_date <= getdate(data['end_date']):
							month_penalty_list.append({"penaltytype": penalty.penalty_type, "apply_date": penalty.apply_date})

			CountItems = Counter(d['penaltytype']
								 for d in penalty_list)
			Count_month_penalty = Counter(d['penaltytype']
										  for d in month_penalty_list)

			for item in list(CountItems):
				if Count_month_penalty[item] == 1:
					calc_using_pre = True

				if (not CountItems[item] == Count_month_penalty[item]) and Count_month_penalty[item]:
					mounth_penalty += self.mounth_penalty_amount(month_penalty_list, item, Count_month_penalty[item], data)


			if mounth_penalty or calc_using_pre:
				penalty_amount = self.pre_penalty_amount(penalty_list, CountItems, data, list(Count_month_penalty))

			d.amount = penalty_amount # + mounth_penalty# Percentagei comment this because it acumelate the amount of last months to current

		else:
			return d.amount
		return d.amount
	def get_taxable_earnings(self, based_on_payment_days=0):
		joining_date, relieving_date = frappe.get_cached_value("Employee", self.employee,
															   ["date_of_joining", "relieving_date"])

		if not relieving_date:
			relieving_date = getdate(self.end_date)

		if not joining_date:
			frappe.throw(_("Please set the Date Of Joining for employee {0}").format(frappe.bold(self.employee_name)))

		taxable_earnings = 0
		additional_income = 0
		additional_income_with_full_tax = 0
		flexi_benefits = 0

		for earning in self.earnings:
			if based_on_payment_days:
				amount, additional_amount = self.get_amount_based_on_payment_days(earning, joining_date, relieving_date)
			else:
				amount, additional_amount = earning.amount, earning.additional_amount

			if earning.is_tax_applicable:
				if additional_amount:
					taxable_earnings += (amount - additional_amount)
					additional_income += additional_amount
					if earning.deduct_full_tax_on_selected_payroll_date:
						additional_income_with_full_tax += additional_amount
					continue

				if earning.is_flexible_benefit:
					flexi_benefits += amount
				else:
					taxable_earnings += amount

		return frappe._dict({
			"taxable_earnings": taxable_earnings,
			"additional_income": additional_income,
			"additional_income_with_full_tax": additional_income_with_full_tax,
			"flexi_benefits": flexi_benefits
		})

	def get_amount_based_on_payment_days(self, row, joining_date, relieving_date):
		amount, additional_amount = row.amount, row.additional_amount
		if (self.salary_structure and
				cint(row.depends_on_payment_days) and cint(self.total_working_days) and
				(not self.salary_slip_based_on_timesheet or
				 getdate(self.start_date) < joining_date or
				 getdate(self.end_date) > relieving_date
				)):
			additional_amount = flt((flt(row.additional_amount) * flt(self.payment_days)
									 / cint(self.total_working_days)), row.precision("additional_amount"))
			amount = flt((flt(row.default_amount) * flt(self.payment_days)
						  / cint(self.total_working_days)), row.precision("amount")) + additional_amount

		elif not self.payment_days and not self.salary_slip_based_on_timesheet and cint(row.depends_on_payment_days):
			amount, additional_amount = 0, 0
		elif not row.amount:
			amount = flt(row.default_amount) + flt(row.additional_amount)

		# apply rounding
		if frappe.get_cached_value("Salary Component", row.salary_component, "round_to_the_nearest_integer"):
			amount, additional_amount = rounded(amount), rounded(additional_amount)

		return amount, additional_amount

	def calculate_unclaimed_taxable_benefits(self, payroll_period):
		# get total sum of benefits paid
		total_benefits_paid = flt(frappe.db.sql("""
			select sum(sd.amount)
			from `tabSalary Detail` sd join `tabSalary Slip` ss on sd.parent=ss.name
			where
				sd.parentfield='earnings'
				and sd.is_tax_applicable=1
				and is_flexible_benefit=1
				and ss.docstatus=1
				and ss.employee=%(employee)s
				and ss.start_date between %(start_date)s and %(end_date)s
				and ss.end_date between %(start_date)s and %(end_date)s
		""", {
			"employee": self.employee,
			"start_date": payroll_period.start_date,
			"end_date": self.start_date
		})[0][0])

		# get total benefits claimed
		total_benefits_claimed = flt(frappe.db.sql("""
			select sum(claimed_amount)
			from `tabEmployee Benefit Claim`
			where
				docstatus=1
				and employee=%s
				and claim_date between %s and %s
		""", (self.employee, payroll_period.start_date, self.end_date))[0][0])

		return total_benefits_paid - total_benefits_claimed

	def get_total_exemption_amount_and_other_incomes(self, payroll_period):
		total_exemption_amount, other_incomes = 0, 0
		if self.deduct_tax_for_unsubmitted_tax_exemption_proof:
			exemption_proof = frappe.db.get_value("Employee Tax Exemption Proof Submission",
												  {"employee": self.employee, "payroll_period": payroll_period.name, "docstatus": 1},
												  ["exemption_amount", "income_from_other_sources"])
			if exemption_proof:
				total_exemption_amount, other_incomes = exemption_proof
		else:
			declaration = frappe.db.get_value("Employee Tax Exemption Declaration",
											  {"employee": self.employee, "payroll_period": payroll_period.name, "docstatus": 1},
											  ["total_exemption_amount", "income_from_other_sources"])
			if declaration:
				total_exemption_amount, other_incomes = declaration

		return total_exemption_amount, other_incomes

	def calculate_tax_by_tax_slab(self, payroll_period, annual_taxable_earning):
		payroll_period_obj = frappe.get_doc("Payroll Period", payroll_period)
		annual_taxable_earning -= flt(payroll_period_obj.standard_tax_exemption_amount)
		data = self.get_data_for_eval()
		data.update({"annual_taxable_earning": annual_taxable_earning})
		taxable_amount = 0
		for slab in payroll_period_obj.taxable_salary_slabs:
			if slab.condition and not self.eval_tax_slab_condition(slab.condition, data):
				continue
			if not slab.to_amount and annual_taxable_earning > slab.from_amount:
				taxable_amount += (annual_taxable_earning - slab.from_amount) * slab.percent_deduction *.01
				continue
			if annual_taxable_earning > slab.from_amount and annual_taxable_earning < slab.to_amount:
				taxable_amount += (annual_taxable_earning - slab.from_amount) * slab.percent_deduction *.01
			elif annual_taxable_earning > slab.from_amount and annual_taxable_earning > slab.to_amount:
				taxable_amount += (slab.to_amount - slab.from_amount) * slab.percent_deduction * .01
		return taxable_amount

	def eval_tax_slab_condition(self, condition, data):
		try:
			condition = condition.strip()
			if condition:
				return frappe.safe_eval(condition, self.whitelisted_globals, data)
		except NameError as err:
			frappe.throw(_("Name error: {0}".format(err)))
		except SyntaxError as err:
			frappe.throw(_("Syntax error in condition: {0}".format(err)))
		except Exception as e:
			frappe.throw(_("Error in formula or condition: {0}".format(e)))
			raise

	def get_salary_slip_row(self, salary_component):
		component = frappe.get_doc("Salary Component", salary_component)
		# Data for update_component_row
		struct_row = frappe._dict()
		struct_row['depends_on_payment_days'] = component.depends_on_payment_days
		struct_row['salary_component'] = component.name
		struct_row['abbr'] = component.salary_component_abbr
		struct_row['do_not_include_in_total'] = component.do_not_include_in_total
		struct_row['is_tax_applicable'] = component.is_tax_applicable
		struct_row['is_flexible_benefit'] = component.is_flexible_benefit
		struct_row['variable_based_on_taxable_salary'] = component.variable_based_on_taxable_salary
		return struct_row

	def get_component_totals(self, component_type):
		total = 0.0
		for d in self.get(component_type):
			if not d.do_not_include_in_total:
				d.amount = flt(d.amount, d.precision("amount"))
				total += d.amount
		return total

	def set_component_amounts_based_on_payment_days(self):
		joining_date, relieving_date = frappe.get_cached_value("Employee", self.employee,
															   ["date_of_joining", "relieving_date"])

		if not relieving_date:
			relieving_date = getdate(self.end_date)

		if not joining_date:
			frappe.throw(_("Please set the Date Of Joining for employee {0}").format(frappe.bold(self.employee_name)))

		for component_type in ("earnings", "deductions"):
			for d in self.get(component_type):
				d.amount = self.get_amount_based_on_payment_days(d, joining_date, relieving_date)[0]

	def set_loan_repayment(self):
		self.set('loans', [])
		self.total_loan_repayment = 0
		self.total_interest_amount = 0
		self.total_principal_amount = 0

		for loan in self.get_loan_details():
			self.append('loans', {
				'loan': loan.name,
				'total_payment': loan.total_payment,
				'interest_amount': loan.interest_amount,
				'principal_amount': loan.principal_amount,
				'loan_account': loan.loan_account,
				'interest_income_account': loan.interest_income_account
			})

			self.total_loan_repayment += loan.total_payment
			self.total_interest_amount += loan.interest_amount
			self.total_principal_amount += loan.principal_amount

	def get_loan_details(self):
		return frappe.db.sql("""select rps.principal_amount, rps.interest_amount, l.name,
				rps.total_payment, l.loan_account, l.interest_income_account
			from
				`tabRepayment Schedule` as rps, `tabLoan` as l
			where
				l.name = rps.parent and rps.payment_date between %s and %s and
				l.repay_from_salary = 1 and l.docstatus = 1 and l.applicant = %s""",
							 (self.start_date, self.end_date, self.employee), as_dict=True) or []

	def update_salary_slip_in_additional_salary(self):
		salary_slip = self.name if self.docstatus==1 else None
		frappe.db.sql("""
			update `tabAdditional Salary` set salary_slip=%s
			where employee=%s and payroll_date between %s and %s and docstatus=1
		""", (salary_slip, self.employee, self.start_date, self.end_date))

	def email_salary_slip(self):
		receiver = frappe.db.get_value("Employee", self.employee, "prefered_email")

		if receiver:
			email_args = {
				"recipients": [receiver],
				"message": _("Please see attachment"),
				"subject": 'Salary Slip - from {0} to {1}'.format(self.start_date, self.end_date),
				"attachments": [frappe.attach_print(self.doctype, self.name, file_name=self.name)],
				"reference_doctype": self.doctype,
				"reference_name": self.name
			}
			if not frappe.flags.in_test:
				enqueue(method=frappe.sendmail, queue='short', timeout=300, is_async=True, **email_args)
			else:
				frappe.sendmail(**email_args)
		else:
			msgprint(_("{0}: Employee email not found, hence email not sent").format(self.employee_name))

	def update_status(self, salary_slip=None):
		for data in self.timesheets:
			if data.time_sheet:
				timesheet = frappe.get_doc('Timesheet', data.time_sheet)
				timesheet.salary_slip = salary_slip
				timesheet.flags.ignore_validate_update_after_submit = True
				timesheet.set_status()
				timesheet.save()

	def set_status(self, status=None):
		'''Get and update status'''
		if not status:
			status = self.get_status()
		self.db_set("status", status)


	def process_salary_structure(self, for_preview=0):
		'''Calculate salary after salary structure details have been updated'''
		if not self.salary_slip_based_on_timesheet:
			self.get_date_details()
		self.pull_emp_details()
		self.get_leave_details(for_preview=for_preview)
		self.calculate_net_pay()

	def pull_emp_details(self):
		emp = frappe.db.get_value("Employee", self.employee, ["bank_name", "bank_ac_no"], as_dict=1)
		if emp:
			self.bank_name = emp.bank_name
			self.bank_account_no = emp.bank_ac_no

	def process_salary_based_on_leave(self, lwp=0):
		self.get_leave_details(lwp=lwp)
		self.calculate_net_pay()

	def unlink_ref_doc_from_salary_slip(ref_no):
		linked_ss = frappe.db.sql_list("""select name from `tabSalary Slip`
		where journal_entry=%s and docstatus < 2""", (ref_no))
		if linked_ss:
			for ss in linked_ss:
				ss_doc = frappe.get_doc("Salary Slip", ss)
				frappe.db.set_value("Salary Slip", ss_doc.name, "journal_entry", "")

	def mounth_penalty_amount(self,month_penalty_list, item, Count_month_penalty, data):
		penalty_amount = 0
		penalty_set = []
		for emp_penalty in month_penalty_list:
			if emp_penalty["penaltytype"] == item not in penalty_set:
				if Count_month_penalty >= 1:
					penalty_set.append(emp_penalty["penaltytype"])
					rule_dict = self.get_penalty_rule(emp_penalty["penaltytype"], emp_penalty['apply_date'], Count_month_penalty)
					formula = rule_dict.strip() if rule_dict else None
					# msgprint("formula=="+str(formula))
					if formula:
						penalty_amount += frappe.safe_eval(formula, None, data)
		return penalty_amount
