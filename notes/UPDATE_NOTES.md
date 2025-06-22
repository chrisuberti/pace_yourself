### Notes for minor updates that are needed for the phase 1 completion


#### app/Visualizations.py
- the plot_power_strategy_summary is mostly useless plots. I do want to save hte trace plot tracking W' out of that so take the funciton and reduce it to just that and rename appropriately

#### 03_Course_Optimization.py 
- Power over the course should be shown as step functions between course segments not a line chart 
    - consider using bar chart

#### app/course.py
- Within the segment breakdown would also be useful to have a column to track energy usage per segment (we already have cumulative)
- 

#### app/optimization.py
- Regarding the overall architecture of the data flow, I'm going to want to use simulate_course_time for the optimization tool so that when the app gets to the point to opimize different powers for different segments we use this as speed solver. 
- However once the optimial power result is computed I want a FINE GRAINED course speed solver that takes in either raw (or slighly smoothed raw) course data and gets a continuous speed prediction given the above pacing strategy
    - Given the results of optimizer.analyze_pacing_strategy(optimization_segments), extrapolate those power values across the duration of the course distance (i.e. if from km 0 to km 1 the perscribed power is 300W, the fine_coures_prediction function will spread the 300W across all those points)
    - The other critical aspect is that we need to also take acceleration into account in the physics engine. So when transitioning from one granular course point to the other, the previous course result speed is the initial speed in the new segment and the algorithim will solve for the acceleration or slowing of the rider as the gradient or power or headwind changes.
    - Iniital speed condition should just be assumed to be the average of first segment from simulate_course_time
    - The resultant finer granularity speed is then passed back to any UX plotting functions

