from setuptools import setup, find_packages

setup(
    name='pace_yourself',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'pandas>=2.3,<3',
        'matplotlib',
        'plotly',
        'pydeck',
        'requests',
        'scipy',
        'scikit-learn',
        'streamlit>=1.52,<1.53',
        'python-dotenv',
        'psycopg[binary]>=3.2,<4',
        'cryptography>=44,<46',
        'sympy'
    ],
)