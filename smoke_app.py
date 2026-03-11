import streamlit as st
st.set_page_config(page_title='Smoke', layout='centered')
st.title('Smoke Test')
st.success('Eger bunu goruyorsan Streamlit render normal calisiyor.')
st.write('Saat:', __import__('datetime').datetime.now().isoformat())
