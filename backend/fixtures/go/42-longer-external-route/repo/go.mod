module example.com/app

go 1.22

replace example.com/dep => ./missing
replace example.com/dep/sub => example.com/dep/sub v1.2.3
