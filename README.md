# Canalchan
Canal-chan's control system, Twitch-plays style controller bot

# What is this?
Canal-chan is a simple bot that collects commands from Twitch chat and passes them right along to vjoy interface. 
Currently the system allows customization of accepted commands and supports button presses and holds. Held buttons are released by simply pressing them again.

More complex control mechanisms can be created via the tcontroller class, that handles the button presses.

# So what are the requirements?

* Twitchio for twitch integration
* vjoy to provide virtual controller
* pyvjoy for controlling vjoy devices

Remember to install configure the vjoy/pyvjoy accordingly. For vjoy to work, place the pyvjoy directory to the folder of this project (eg. "Canalchan-master/pyvjoy").

# Who is this Canal anyways?
Canal Vorfeed, fictional AI with mind of her own. Seemed fitting.
