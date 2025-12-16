"""
Debug helpers for Streamlit applications
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Any, Dict

def inspect_session_state(expanded: bool = False, show_in_sidebar: bool = False):
    """
    Display a comprehensive view of the Streamlit session state.
    
    Args:
        expanded: Whether to show the expander expanded by default
        show_in_sidebar: Whether to show in sidebar instead of main area
    """
    container = st.sidebar if show_in_sidebar else st
    
    with container.expander("🔍 Session State Inspector", expanded=expanded):
        if not st.session_state:
            st.write("Session state is empty")
            return
        
        st.write(f"**Total keys: {len(st.session_state)}**")
        
        # Show keys list
        keys = list(st.session_state.keys())
        st.write("**Keys:**", ", ".join(f"`{k}`" for k in keys))
        
        # Detailed inspection
        for key in sorted(keys):
            value = st.session_state[key]
            
            st.write(f"### `{key}`")
            
            # Type information
            value_type = type(value).__name__
            st.write(f"**Type:** `{value_type}`")
            
            # Special handling for different types
            if value is None:
                st.write("**Value:** `None`")
            
            elif isinstance(value, (str, int, float, bool)):
                st.write(f"**Value:** `{value}`")
            
            elif isinstance(value, (list, tuple)):
                st.write(f"**Length:** {len(value)}")
                if len(value) > 0:
                    st.write(f"**First item type:** `{type(value[0]).__name__}`")
                    if len(value) <= 5:
                        st.write("**Contents:**")
                        for i, item in enumerate(value):
                            st.write(f"  [{i}]: {str(item)[:100]}{'...' if len(str(item)) > 100 else ''}")
                    else:
                        st.write("**Sample (first 3):**")
                        for i in range(3):
                            st.write(f"  [{i}]: {str(value[i])[:100]}{'...' if len(str(value[i])) > 100 else ''}")
            
            elif isinstance(value, dict):
                st.write(f"**Keys:** {len(value)}")
                if len(value) <= 10:
                    for k, v in value.items():
                        v_str = str(v)[:50] + ('...' if len(str(v)) > 50 else '')
                        st.write(f"  `{k}`: {v_str}")
                else:
                    sample_keys = list(value.keys())[:5]
                    st.write(f"**Sample keys:** {sample_keys}")
            
            elif isinstance(value, pd.DataFrame):
                st.write(f"**Shape:** {value.shape}")
                st.write(f"**Columns:** {list(value.columns)}")
                if not value.empty:
                    st.write("**Sample data:**")
                    st.dataframe(value.head(3))
            
            elif hasattr(value, '__dict__'):
                # For custom objects, show attributes
                st.write("**Object attributes:**")
                attrs = [attr for attr in dir(value) if not attr.startswith('_')]
                for attr in attrs[:10]:  # Show first 10 attributes
                    try:
                        attr_value = getattr(value, attr)
                        if callable(attr_value):
                            st.write(f"  `{attr}()`: method")
                        else:
                            attr_str = str(attr_value)[:50] + ('...' if len(str(attr_value)) > 50 else '')
                            st.write(f"  `{attr}`: {attr_str}")
                    except Exception:
                        st.write(f"  `{attr}`: <unable to access>")
                
                if len(attrs) > 10:
                    st.write(f"  ... and {len(attrs) - 10} more attributes")
            
            else:
                # Generic handling
                value_str = str(value)
                if len(value_str) > 200:
                    value_str = value_str[:200] + "..."
                st.write(f"**Value:** {value_str}")
            
            st.write("---")

def clear_session_state_key(key: str):
    """Clear a specific session state key"""
    if key in st.session_state:
        del st.session_state[key]
        st.success(f"Cleared session state key: `{key}`")
    else:
        st.warning(f"Key `{key}` not found in session state")

def session_state_manager():
    """
    Interactive session state manager widget
    """
    st.subheader("🛠️ Session State Manager")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Refresh Inspector"):
            st.rerun()
        
        if st.button("🗑️ Clear All Session State", type="secondary"):
            st.session_state.clear()
            st.success("Cleared all session state")
            st.rerun()
    
    with col2:
        # Clear specific key
        if st.session_state:
            key_to_clear = st.selectbox(
                "Clear specific key:",
                options=[""] + list(st.session_state.keys())
            )
            
            if key_to_clear and st.button(f"Clear `{key_to_clear}`"):
                clear_session_state_key(str(key_to_clear))
                st.rerun()
    
    # Show inspector
    inspect_session_state(expanded=True)

def quick_debug_info():
    """Show quick debug info in a compact format"""
    keys_str = ', '.join(str(k) for k in list(st.session_state.keys())[:5])
    st.caption(f"🔍 Session State: {len(st.session_state)} keys | Main keys: {keys_str}")
