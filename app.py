import streamlit as st
import pandas as pd
import json
import requests
import re
from typing import Dict, List, Any

# --- Page Config ---
st.set_page_config(
    page_title="Major & Minor Fulfillment Checker",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 1. Data Loading (Cached) ---
@st.cache_data
def load_data():
    """
    Fetches JSON data directly from the raw GitHub content.
    This avoids the need for git cloning and works better in cloud environments.
    """
    base_url = "https://raw.githubusercontent.com/RichardLin3/InfoSysProj/main/data/"
    files = {
        "minor_data": "minors_v3.json",
        "gened_data": "gened_v2.json",
        "major_data": "all-majors.json",
        "lib_data": "liberal_arts_courses.json",
        "ID_data": "ID.json"
    }
    
    loaded_data = {}
    
    with st.spinner('Loading Curriculum Data...'):
        for key, filename in files.items():
            try:
                response = requests.get(base_url + filename)
                response.raise_for_status()
                loaded_data[key] = response.json()
            except Exception as e:
                st.error(f"Error loading {filename}: {e}")
                return None

    return loaded_data

# --- 2. Processing Functions ---

def get_minor_courses(selected_minor, minor_data):
    """Extracts course codes from the minor data."""
    courses = []
    if selected_minor in minor_data:
        minor_info = minor_data[selected_minor]
        for section_list in minor_info.values():
            for entry in section_list:
                if isinstance(entry, dict) and 'Course' in entry:
                    courses.append(entry['Course'])
                elif isinstance(entry, dict):
                    # Handle nested options like "Choose 1"
                    for value in entry.values():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict) and 'Course' in item:
                                    courses.append(item['Course'])
    return courses

def map_gened_requirements(courses, selected_major, data_bundle):
    """Maps courses to their fulfilled requirements."""
    gened_data = data_bundle['gened_data']
    major_data = data_bundle['major_data']
    lib_data = data_bundle['lib_data']
    ID_data = data_bundle['ID_data']
    
    # Pre-process GenEd Map
    gened_fulfillment_map = {}
    for core_type in ['Required Core', 'Flexible Core']:
        for course_info in gened_data['gened'][core_type]:
            areas = course_info.get('Area(s)', [])
            gened_fulfillment_map[course_info['Course']] = areas

    # Sets for lookup
    major_core = set([c['Course'] for c in major_data[selected_major]['Core']])
    major_elective = set([c['Course'] for c in major_data[selected_major]['Electives']])
    adv_lib = set([c['Course'] for c in lib_data['Adv Lib Art']])
    lib_art = set([c['Course'] for c in lib_data['Lib Art']])

    course_gened_fulfillment_list = []

    for course in courses:
        fulfilled_geneds = gened_fulfillment_map.get(course, [])
        if not isinstance(fulfilled_geneds, list):
            fulfilled_geneds = [fulfilled_geneds] if fulfilled_geneds else []
        
        # Make a copy to avoid modifying the reference
        current_fulfilled = list(fulfilled_geneds)

        if course in major_core:
            current_fulfilled.append('Major_Core')
        if course in major_elective:
            current_fulfilled.append('Major_Elec')
        if course in lib_art:
            current_fulfilled.append('Lib Art')
        if course in adv_lib:
            current_fulfilled.append('Lib Art')
            current_fulfilled.append('Adv Lib Art')
        
        # Check ID fulfillment
        # Note: ID_data is a dictionary, checking keys
        if course in ID_data or re.search(r'\d+ID$', course):
            current_fulfilled.append('ID')

        course_gened_fulfillment_list.append({
            'Courses in Minor': course,
            'Fulfilled Areas': current_fulfilled
        })
        
    return course_gened_fulfillment_list

def process_curriculum_json(curriculum_name: str, curriculum_data: Dict[str, Any],
                            gened_areas: List[str], fulfillment_list: List[Dict]) -> pd.DataFrame:
    """Processes the curriculum JSON into a MultiIndex DataFrame."""
    
    data = curriculum_data
    fulfillment_map = {item['Courses in Minor']: item['Fulfilled Areas'] for item in fulfillment_list}
    processed_list = []

    def format_credit(min_credit: int, max_credit: int) -> str:
        return str(max_credit) if min_credit == max_credit else f"{min_credit}-{max_credit}"

    def get_credit_info(data_item: Dict[str, Any]) -> Dict[str, int]:
        info = data_item.get('Credit') or data_item.get('credit')
        if info: return info
        for key, value in data_item.items():
            if isinstance(key, str) and 'credit' in key.lower():
                if isinstance(value, dict) and 'Min' in value and 'Max' in value:
                    return value
        return {'Min': 3, 'Max': 3}

    # --- CORE Courses ---
    core_section = data.get("Core", [])
    section_name = f"1. {curriculum_name} Core Requirements"

    for item in core_section:
        if "Course" in item:
            course = item['Course']
            credit_info = get_credit_info(item)
            processed_list.append({
                'Sub_Section': 'A. Mandatory Core Courses',
                'Courses in Minor': course,
                'Name': item.get('Title', 'Mandatory'),
                'Credit': format_credit(credit_info['Min'], credit_info['Max']),
                'Fulfilled Areas': fulfillment_map.get(course, [])
            })
        elif "group" in item:
            sub_section_name = f'B. Conditional Core: {item["group"]}'
            for course_info in item['courses']:
                course = course_info['Course']
                credit_info = get_credit_info(course_info)
                processed_list.append({
                    'Sub_Section': sub_section_name,
                    'Name': course_info.get('Title', ''),
                    'Courses in Minor': course,
                    'Credit': format_credit(credit_info['Min'], credit_info['Max']),
                    'Fulfilled Areas': fulfillment_map.get(course, [])
                })

    # --- ELECTIVE Courses ---
    elective_section = data.get("Electives", [])
    
    for item in elective_section:
        if "Course" in item:
            course = item['Course']
            credit_info = get_credit_info(item)
            processed_list.append({
                'Sub_Section': "A. General Electives List",
                'Name': item.get('Title', ''),
                'Courses in Minor': course,
                'Credit': format_credit(credit_info['Min'], credit_info['Max']),
                'Fulfilled Areas': fulfillment_map.get(course, [])
            })
        elif "group" in item:
            sub_section_name = f'B. Conditional Elective: {item["group"]}'
            for course_info in item['courses']:
                course = course_info['Course']
                credit_info = get_credit_info(course_info)
                processed_list.append({
                    'Sub_Section': sub_section_name,
                    'Courses in Minor': course,
                    'Name': course_info.get('Title', ''),
                    'Credit': format_credit(credit_info['Min'], credit_info['Max']),
                    'Fulfilled Areas': fulfillment_map.get(course, [])
                })

    # --- Create DataFrame ---
    course_fulfillment_list_for_df = []
    for course_info in processed_list:
        course_dict = {
            'Name': course_info['Name'],
            'Sub_Section': course_info['Sub_Section'],
            'Courses in Minor': course_info['Courses in Minor'],
            'Credit': course_info['Credit'],
        }
        fulfilled_areas = course_info['Fulfilled Areas']
        for gened_abbr in gened_areas:
            course_dict[gened_abbr] = 'X' if gened_abbr in fulfilled_areas else ''
        course_fulfillment_list_for_df.append(course_dict)

    df = pd.DataFrame(course_fulfillment_list_for_df).fillna('')
    if not df.empty:
        df = df.set_index(['Sub_Section','Courses in Minor', 'Name'])
        column_order = ['Credit'] + gened_areas
        df = df.reindex(columns=column_order, fill_value='')
    
    return df

# --- 3. Styling Functions ---

def apply_row_styles(s):
    return ['' for _ in s]

def apply_section_borders(styler):
    styles = []
    index_values = styler.index.values
    for i in range(len(index_values)):
        current_subsection = index_values[i][0]
        if (i + 1 < len(index_values) and index_values[i+1][0] != current_subsection):
            light_border_rule = {
                'selector': f'tr:nth-child({i + 1}) th, tr:nth-child({i + 1}) td',
                'props': [('border-bottom', '4px solid #cccccc !important')]
            }
            styles.append(light_border_rule)
    return styles

# --- 4. Main App Logic ---

def main():
    st.title("🎓 Degree Audit: Major & Minor Intersection")
    st.markdown("Select your **Major** and **Minor** to see how minor courses fulfill GenEd, Major, and Liberal Arts requirements.")
    
    data_bundle = load_data()
    
    if not data_bundle:
        st.stop()

    # Sidebar Selection
    st.sidebar.header("Configuration")
    
    major_list = list(data_bundle['major_data'].keys())
    minor_list = list(data_bundle['minor_data'].keys())
    
    selected_major = st.sidebar.selectbox("Select Major:", major_list)
    selected_minor = st.sidebar.selectbox("Select Minor:", minor_list)

    if st.sidebar.button("Analyze Intersection"):
        
        # 1. Get Courses
        courses = get_minor_courses(selected_minor, data_bundle['minor_data'])
        
        if not courses:
            st.warning(f"No course data found for minor: {selected_minor}")
            return

        # 2. Map Requirements
        course_gened_fulfillment_list = map_gened_requirements(courses, selected_major, data_bundle)
        
        # 3. Process into DataFrame
        gened_areas = ['EC', 'MQR', 'LPS', 'WCGI', 'USED', 'IS', 'CE', 'SW' ,'Lib Art', 'Adv Lib Art', 'ID', 'Major_Core','Major_Elec']
        
        final_df = process_curriculum_json(
            selected_minor,
            data_bundle['minor_data'][selected_minor],
            gened_areas,
            course_gened_fulfillment_list
        )

        if final_df.empty:
            st.info("The selected minor curriculum data structure could not be processed into the table format.")
        else:
            # 4. Apply Styles
            styled_df = (
                final_df.style
                .set_properties(**{'border': '1px solid #cccccc'})
                .apply(apply_row_styles, axis=1)
                .set_caption(f'{selected_major} Major and {selected_minor} Minor Course Fulfillment Overview')
                .set_table_styles(apply_section_borders(final_df.style), overwrite=False)
                .set_table_styles([
                    {'selector': 'caption', 'props': [('font-size', '20px'), ('font-weight', 'bold'), ('margin-bottom', '10px')]},
                    {'selector': 'th.col_heading', 'props': [('text-align', 'center'), ('padding', '8px'), ('background-color', '#f0f2f6')]},
                    {'selector': 'th.row_heading', 'props': [('vertical-align', 'top'), ('text-align', 'left'), ('padding', '8px'), ('border-bottom', '1px solid #999999 !important')]},
                    {'selector': 'td', 'props': [('text-align', 'center')]},
                    {'selector': 'tr:hover th', 'props': [('background-color', '#e0e0e0 !important'), ('color', '#333333 !important')]},
                    {'selector': 'tr:hover td', 'props': [('background-color', '#eeeeee !important')]}
                ])
            )
            
            # 5. Render
            st.write(styled_df.to_html(), unsafe_allow_html=True)
            
            # Legend
            with st.expander("ℹ️ Legend"):
                st.markdown("""
                * **Major_Core**: Fulfills a Major Core requirement.
                * **Major_Elec**: Fulfills a Major Elective requirement.
                * **Lib Art**: Counts as Liberal Arts.
                * **Adv Lib Art**: Counts as Advanced Liberal Arts.
                * **ID**: Interdisciplinary course.
                """)

if __name__ == "__main__":
    main()