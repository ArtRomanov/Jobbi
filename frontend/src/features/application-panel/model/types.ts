/**
 * Form values mirror the editable fields of an application.
 * Numeric fields use string representation for form inputs;
 * we convert back to numbers before sending to the API.
 */
export interface FormValues {
  company_name: string;
  role_title: string;
  job_url: string;
  salary_min: string;
  salary_max: string;
  salary_currency: string;
  contact_name: string;
  contact_email: string;
  notes: string;
  status: string;
}
