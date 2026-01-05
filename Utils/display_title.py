# Script update for Jixovox database utilities - updated 2026-01-05 09:37 UTC by lloydlewis
import os
from Utils.colors import YELLOW,BRIGHT,GREEN


def display_title(color=YELLOW+BRIGHT):
    os.system('cls' if os.name == 'nt' else 'clear')
    print(color+"""
                    ██╗██╗██╗  ██╗ ██████╗ ██╗   ██╗ ██████╗ ██╗  ██╗ by
                    ██║██║╚██╗██╔╝██╔═══██╗██║   ██║██╔═══██╗╚██╗██╔╝ lloyd
                    ██║██║ ╚███╔╝ ██║   ██║██║   ██║██║   ██║ ╚███╔╝  lewizzz ;)
               ██   ██║██║ ██╔██╗ ██║   ██║╚██╗ ██╔╝██║   ██║ ██╔██╗ 
               ╚█████╔╝██║██╔╝ ██╗╚██████╔╝ ╚████╔╝ ╚██████╔╝██╔╝ ██╗
                ╚════╝ ╚═╝╚═╝  ╚═╝ ╚═════╝   ╚═══╝   ╚═════╝ ╚═╝  ╚═╝ """,GREEN +"""V 1.0
                                                                                                                                        
""")
    

display_title()
