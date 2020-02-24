# -*- coding: utf-8 -*-
# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from erpnext.hr.doctype.employee.employee import is_holiday
from erpnext.hr.report.monthly_attendance_sheet.monthly_attendance_sheet import get_employee_details, get_holiday
from frappe import msgprint,_
import json
from frappe.utils import cstr, getdate, now_datetime
from frappe.model.document import Document
from datetime import timedelta, date, datetime


class EmployeeAttendanceTool(Document):
	pass

@frappe.whitelist()
def get_employees(date, department=None, branch=None, company=None, attendance_type =None,end_date=None):
	attendance_not_marked = []
	attendance_marked = []
	filters = {"status": "Active"}
	if department != "All":
		filters["department"] = department
	if branch != "All":
		filters["branch"] = branch
	if company != "All":
		filters["company"] = company
	# if attendance_type != "All":
	# 	frappe.msgprint(attendance_type)
	# 	filters["attendance_type"] = frappe.get_list("Attendance Period", filters=[["attendance_type","=",attendance_type]], fields=["name"])
	
	employee_list = frappe.get_list("Employee", \
		fields=["employee", "employee_name"], \
		filters=filters, order_by="employee_name"
		)

	marked_employee = {}
	employee_attendance_list = frappe.db.sql(
		"""
		select employee, `status`
			from `tabAttendance` 
				where `tabAttendance`.attendance_date = %s 
				and `tabAttendance`.attend_time is not null  
				and `tabAttendance`.leave_time  is not null 
			order by `tabAttendance`.docstatus asc, `tabAttendance`.`modified` DESC
		"""
			, (date), as_dict=True,debug=False
		)
		# for emp in frappe.get_list("Attendance", fields=["employee", "status"],\
		#                         filters=[
		# 								["attendance_date","=" , date] \
		#                                 , ["attend_time", "is null", None] \
		# 								, ["leave_time", "is null", None]
		# 								]
		# 	,debug=True):
	for emp in employee_attendance_list:
		marked_employee[emp['employee']] = emp['status']

	for employee in employee_list:
		employee['status'] = marked_employee.get(employee['employee'])
		if employee['employee'] not in marked_employee:
			attendance_not_marked.append(employee)
		else:
			attendance_marked.append(employee)
	return {
		"marked": attendance_marked,
		"unmarked": employee_list
	}

@frappe.whitelist()
def mark_employee_attendance(employee_list, status, date, leave_type=None, company=None):
	employee_list = json.loads(employee_list)
	for employee in employee_list:
		attendance = frappe.new_doc("Attendance")
		attendance.employee = employee['employee']
		attendance.employee_name = employee['employee_name']
		attendance.attendance_date = date
		attendance.status = status
		if status == "On Leave" and leave_type:
			attendance.leave_type = leave_type
		if company:
			attendance.company = company
		else:
			attendance.company = frappe.db.get_value("Employee", employee['employee'], "Company")
		attendance.submit()

@frappe.whitelist()
def attendence_proccessing(employee_list, status, start_date, leave_type=None, company=None, end_date=None):
	validate_dates(start_date,end_date)
	employee_list = json.loads(employee_list)
	
	days_types = {"Present": "P", "Absent": "A", "Half Day": "HD", "On Leave": "L", "None": "", "Unallocated":"<b>U</b>"}
	dict_days = frappe._dict()

	start_date, end_date = getdate(start_date), getdate(end_date)
	leave_type = ""

	for single_date in daterange(start_date, end_date):
		curr_single_date = getdate(single_date)
		# is_holiday = False
		for employee in employee_list:
			employee["date"] = curr_single_date
			attendance_log = get_emp_log(curr_single_date, employee["employee"])
			# frappe.msgprint(str(attendance_log))
			if attendance_log==[]:
				is_leave_mission_rest = check_leave_mission_rest(employee["employee"],curr_single_date)
				if (not is_leave_mission_rest) and (not is_holiday(employee["employee"],curr_single_date)):
					add_attendance(employee, "Absent", curr_single_date, attend_time="", leave_time="")
			else:
				# Check if Emp is Assigned to Period and return Period data
				emp_data_Dic = check_assigned_period(employee['employee'],curr_single_date)

				if emp_data_Dic == []:
					dict_days[curr_single_date]=days_types["Unallocated"]# =======> to store days without period
				elif(emp_data_Dic["attendance_type"] == "Shift"):
					attend_time = None # اول معاد حضور
					leave_time = ""  # معاد الانصراف
					attend_notes = ""
					late_minutes = 0.0
					has_signed_after_permission = False
					after_period_end_time = False
					atendance_time_margin = frappe.db.get_single_value("Attendances Settings", "attendance_time_margin", cache=False)
					max_limit_for_attend = frappe.db.get_single_value("Attendances Settings", "max_limit_for_attendance", cache=False)
					
					time_margin_after_leave_time = frappe.db.get_single_value("Attendances Settings", "leave_time_margin", cache=False)
					
					for item in attendance_log:
						#---------------------------------------Attend Variables----------------------------------------------
						max_time_after_attend = emp_data_Dic["start_time"] + timedelta(minutes=int(emp_data_Dic["attendance_permissibility"]))
						max_time_before_attend = emp_data_Dic["start_time"] - timedelta(minutes=int(atendance_time_margin))
						max_limit_for_attendance = emp_data_Dic["start_time"] + timedelta(minutes=int(max_limit_for_attend))

						#---------------------------------------Leave Variables----------------------------------------------
						start_time_to_leave = emp_data_Dic["end_time"] - timedelta(minutes=int(emp_data_Dic["leave_permissibility"]))
						max_time_to_leave = emp_data_Dic["end_time"] + timedelta(minutes=int(time_margin_after_leave_time))
						#-----------------------------------------------------------------------------------------------------

						item_time_stamp = datetime.strptime(item["timestamp"], "%H:%M:%S")
						item_time_stamp = timedelta(hours=item_time_stamp.hour, minutes=item_time_stamp.minute, seconds=item_time_stamp.second)

						# حضور قبل الموعد
						# During Attendance Time Margin (Before Period Start Time)
						if(emp_data_Dic["start_time"] > item_time_stamp >= max_time_before_attend):
							attend_time = item_time_stamp
							attend_notes = "حضور قبل الموعد"

						# حضور قبل الموعد وقبل فنرة الحضور المبكر
						elif(emp_data_Dic["start_time"] > item_time_stamp < max_time_before_attend):
							attend_time = ""
							attend_notes = "حضور مبكر"
	
						# حضور في الموعد أو خلال فترة السماحية
						elif((emp_data_Dic["start_time"] <= item_time_stamp <= max_time_after_attend)):
							attend_time = item_time_stamp  # حضور اول معاد
							attend_notes = "حضور يومى"

						#حضور بعد وقت الفترة وبعد وقت السماحية	
						elif (item_time_stamp > max_time_after_attend):
							if check_permission(employee['employee'], curr_single_date,late_attend=True) and (not has_signed_after_permission):# إذن الحضور
								attend_time = item_time_stamp  # إذن حضور
								attend_notes = "إذن حضور"
								has_signed_after_permission = True

							elif(item_time_stamp < max_limit_for_attendance):
								attend_time = item_time_stamp  # حضور مع التاخير
								attend_notes = " حضور مع التأخير"
								late_seconds = (attend_time - max_time_after_attend).total_seconds()
								late_minutes = late_seconds / 60 #تأخير عن ميعاد الحضور
						#-------------------------------------------Leave Conditions-------------------------------------------------
							elif(item_time_stamp < start_time_to_leave):
								if check_permission(employee['employee'], curr_single_date,late_attend=False):
									attend_notes += "- اذن انصراف مبكر "
								else:
									attend_notes +="-  إنصراف قبل الموعد "
								leave_time = item_time_stamp

							elif(start_time_to_leave <= item_time_stamp <= max_time_to_leave):
								leave_time = item_time_stamp
								attend_notes += "-  إنصراف يومى "
								
							elif(item_time_stamp > max_time_to_leave):
								attend_notes += "-  إنصراف بعد الموعد "
								leave_time = ""
								after_period_end_time =True

					if attend_time and (not leave_time):
						if not after_period_end_time:
							attend_notes += "- عدم توقيع انصراف"
							
					add_attendance(employee, status, curr_single_date, attend_time, leave_time, late_minutes, attend_notes,leave_type)
				elif(emp_data_Dic["attendance_type"] in ("Open Day","Flexible Hours")):
					attend_time = None # اول معاد حضور
					leave_time = ""  # معاد الانصراف
					attend_notes = ""
					current_timestamp_to_handle = ""
					total_hours_per_day = "00:00:00" 
					for item in attendance_log:
						item_time_stamp = datetime.strptime(item["timestamp"], "%H:%M:%S")
						item_time_stamp = timedelta(hours=item_time_stamp.hour, minutes=item_time_stamp.minute, seconds=item_time_stamp.second)

						if attend_time==None:
							attend_time = item_time_stamp
							current_timestamp_to_handle = item_time_stamp
							status = "Present"
							attend_notes = "حضور يومى"
							
						elif(current_timestamp_to_handle==""):
							current_timestamp_to_handle = item_time_stamp
							
						elif(current_timestamp_to_handle != "" and (item_time_stamp - current_timestamp_to_handle) > timedelta(minutes=5)):
							temp = (item_time_stamp - current_timestamp_to_handle)
							temp = str(datetime.strptime(str(temp),"%H:%M:%S")).split(' ')[1]
							
							total_hours_per_day = \
							timedelta(hours=int(str(temp).split(':')[0]), minutes=int(str(temp).split(':')[1]), seconds=int(str(temp).split(':')[1])) + \
							timedelta(hours=int(str(total_hours_per_day).split(':')[0]), minutes=int(str(total_hours_per_day).split(':')[1]), seconds=int(str(total_hours_per_day).split(':')[2]))
							current_timestamp_to_handle = ""
							
						leave_time = item_time_stamp
						
					add_attendance(employee, status, curr_single_date, attend_time, leave_time, 0.0, attend_notes,leave_type,daily_hours=str(total_hours_per_day))
					
def add_attendance(employee, status, date, attend_time=None, leave_time=None, late_minutes=0.0, attend_notes=None, leave_type=None,daily_hours = None):
		# delete existing row
		del_attendance(employee, date)

		attendance = frappe.new_doc("Attendance")
		attendance.employee = employee['employee']
		attendance.employee_name = employee['employee_name']
		attendance.attendance_date = date
		attendance.attend_time = attend_time
		attendance.leave_time = leave_time
		attendance.delay_minutes = late_minutes
		attendance.notes = attend_notes
		attendance.status = status
		attendance.daily_hours = daily_hours

		attendance.company = frappe.db.get_value("Employee", employee['employee'], "Company")

		if status == "On Leave" and leave_type:
			attendance.leave_type = leave_type
		
		
		attendance.submit()

def del_attendance(employee, date):
	frappe.db.sql(
		"""
		delete
			from `tabAttendance`
    			where employee = %s
					and attendance_date=%s
		""", (employee['employee'], date), debug=False
	)

def check_permission(employee, curr_single_date,late_attend=False):
	if late_attend:
		cond=''' and permission_type = 'Late Attend' '''
	else:
		cond = ''' and  permission_type = 'Early leave' '''
	is_permission = frappe.db.sql(
		"""
        SELECT * 
            from `tabPermission`
                where employee = %s and for_date=%s """
            +cond+
			""" and docstatus < 2 
        """, (employee, curr_single_date), debug=False, as_list=True
	)
	return is_permission

def check_leave_mission_rest(employee, curr_single_date):
	is_leave_mission_rest = frappe.db.sql(
		"""
        SELECT * 
            from `tabAttendance`
                where employee = %s
                    and attendance_date=%s and status in ('Mission','Rest','On Leave')
        """, (employee, curr_single_date), debug=False, as_list=True
	)
	return is_leave_mission_rest

def get_emp_log(log_date,employee):
	return frappe.db.sql(
		"""
		select user_id, substring_index(substring_index(`timestamp`,' ',-1),'.' ,1) `timestamp`, device
			from `tabAttendance Log`
			where employee=%s
				and `timestamp` like %s
		order by `timestamp`
		""", (employee,cstr(log_date)+"%" ), as_dict=1, debug=False
	)

def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days+1)):
        yield start_date + timedelta(n)

def check_assigned_period(employee_name, curr_single_date):
	data_Dic = frappe.db.sql(
		"""
		select AD.attendance_period , AD.start_date , AD.end_date end_date, 
		AP.start_date Pstart_date, AP.end_date Pend_date,AP.start_time,AP.end_time, 
		AP.attendance_permissibility, AP.leave_permissibility, AP.attendance_type, 
		AP.night_shift, AP.hours_per_month, AP.hours_per_day
			from `tabAttendance Data` AD
			INNER JOIN 
			`tabAttendance Period` AP
			on AD.attendance_period = AP.`name`
			and AD.parent=%s
			and %s between AD.start_date and ifnull(AD.end_date,CURDATE())
		"""
		, (employee_name, curr_single_date), as_dict=1, debug=False
		)

	if data_Dic!=[]:
		return data_Dic[0]
	
	return data_Dic

def validate_dates(start_date,end_date):
	today = now_datetime().date()
	if getdate(end_date) > today:
		frappe.throw(_("End Date cannot be After Today"))
	if getdate(start_date) > getdate(end_date):
		frappe.throw(_("Start date cannot be After End date"))