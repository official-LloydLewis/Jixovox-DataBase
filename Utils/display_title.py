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
                ╚════╝ ╚═╝╚═╝  ╚═╝ ╚═════╝   ╚═══╝   ╚═════╝ ╚═╝  ╚═╝ """,GREEN +"""V 0.1 beta
                                                                                                                                        
""")
    

display_title()