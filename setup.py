from setuptools import setup, find_packages

setup(
    name='pace_yourself',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'pandas',
        'matplotlib',
        'plotly',
        'pydeck',
        'requests',
        'scipy',
        'scikit-learn',
        'streamlit',
        'python-dotenv',
        'sympy'
    ],
)