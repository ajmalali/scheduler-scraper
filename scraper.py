from models.courses import Course
from models.sections import Section
from bs4 import BeautifulSoup
import requests
import logging

logging.basicConfig(filename="logs.log", level=logging.INFO)
# truncating log file before new run
with open('logs.log', 'w'):
    pass

class Scraper():

    def __init__(self):
        self.depts = []
        self.terms = []
        self.__VIEWSTATEGENERATOR = ""
        self.__EVENTVALIDATION = ""
        self.__VIEWSTATE = ""
        self.url = "https://registrar.kfupm.edu.sa/CourseOffering"
        self.session = requests.Session()

        try:
            response = self.session.get(self.url)
        except requests.RequestException as e:
            logging.error(e)

        self.soup = BeautifulSoup(response.text, 'html.parser')

    def setDepartments(self):
        '''Initializes dept with all available departments'''

        options = self.soup.find(id="CntntPlcHldr_ddlDept")

        for value in options.find_all("option"):
            self.depts.append(value.get("value"))      
        
        logging.info(f"Depts acquired: {self.depts}")

    def setTerms(self, limit=3):
        '''Initializes term with the 3 most recent terms'''

        for term in self.soup.find(id="CntntPlcHldr_ddlTerm").find_all("option"):
            self.terms.append(term.get("value"))

        self.terms = self.terms[:limit]
        logging.info(f"Terms acquired: {self.terms}")

    def setFormAttributes(self):
        '''Initializes form attributes necessary for submission'''

        self.__VIEWSTATEGENERATOR = self.soup.find(
            "input", id="__VIEWSTATEGENERATOR").get("value")
        self.__VIEWSTATE = self.soup.find(
            "input", id="__VIEWSTATE").get("value")
        self.__EVENTVALIDATION = self.soup.find(
            "input", id="__EVENTVALIDATION").get("value")
        
    def getPayload(self, term, dept) -> dict:
    
        payload = {
            '__VIEWSTATE': self.__VIEWSTATE,
            '__VIEWSTATEGENERATOR': self.__VIEWSTATEGENERATOR,
            '__EVENTVALIDATION': self.__EVENTVALIDATION,
            'ctl00$CntntPlcHldr$ddlTerm': term,
            'ctl00$CntntPlcHldr$ddlDept': dept
        }
        
        return payload
        
    def getCourseData(self, row) -> dict:
        '''Iterates and initializes attributes of ONE course'''
        
        data = {}
        
        for inner in row.find_all("div", class_="tdata"):
            # Some courses are structured with an additional
            # ":" in their name and hence cause an error
            # when unpacking with just inner.text.split(":").
            # Anything after the first ":" is going to be the
            # value of the attribute, hence maxsplit=1
            key, value = inner.text.split(":", maxsplit=1)
            data[key] = value

        return data

            
    def getData(self, courses: dict) -> list:
        """
        Scrapes the KFUPM Course offering page and returns a
        courses list containing course objects
        """

        # Initializing necessary attributes
        self.setTerms()
        self.setDepartments()
        self.setFormAttributes()

        for term in self.terms:
            for dept in self.depts:
                logging.info(f"\t{term}: {dept}")
                
                try:
                    response = self.session.post(self.url, data=self.getPayload(term, dept))
                except requests.RequestException as e:
                    logging.error(e)

                soup = BeautifulSoup(response.text, 'html.parser')
                numberOfCourses = 0

                for row in soup.find_all("div", class_="trow"):
                    # fetch data of ONE course
                    data = self.getCourseData(row)
                        
                    # splitting course name and sections
                    # as required by the schema
                    data["Section"], data["Course"] = (
                        data["Course-Sec"].split("-")[1],
                        data["Course-Sec"].split("-")[0]
                    )
                    # splitting Time as start_time and
                    # end_time as required by schema
                    data["start_time"], data["end_time"] = (
                        data["Time"].split("-")[0],
                        data["Time"].split("-")[1]
                    )
                    
                    # setting time as -1 to indicate 
                    # that the start_time / end_time 
                    # fields are empty 
                    if len(data["start_time"]) == 0:
                        data["start_time"] = -1
                        
                    if len(data["end_time"]) == 0:
                        data["end_time"] = -1
                    
                    # removing redundant keys
                    data.pop("Course-Sec", None)
                    data.pop("Time", None)
                    numberOfCourses += 1
                                        
                    # storing name and term of latest course scraped
                    # to check whether the previous course that was
                    # scraped is the same so as to only append a
                    # new section to the course object
                    courseID = data["Course"] + term
                    
                    section = Section(
                            data["CRN"],
                            data["Section"],
                            data["Instructor"],
                            data["Activity"],
                            data["Day"],
                            data["Loc"],
                            data["start_time"],
                            data["end_time"],
                            data["Status"]                                                        
                        )

                    # If the new course does not already exist, create a new
                    # course object and append it to the courses dict,
                    # otherwise only create a new section object and
                    # append it to courses.sections
                    if (courseID not in courses):                        
                        sections = []
                        sections.append(section)

                        course = Course(
                            data["Course"],
                            data["Course Name"],
                            term,
                            dept,
                            sections
                        )

                    else:
                        # Only appends the new section of the same course
                        courses[courseID].sections.append(section)
                        
                    # Set course to unique courseID
                    courses[courseID] = course
                    logging.info(f"\t {courseID} created")

        return courses
